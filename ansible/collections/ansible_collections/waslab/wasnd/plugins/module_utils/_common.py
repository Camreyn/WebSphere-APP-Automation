# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import contextlib
import os
import re
import shutil
import stat
import tempfile


DEFAULT_INSTALL_ROOT = "/opt/WebSphere/AppServers"
DEFAULT_IM_ROOT = "/opt/IBM/InstallationManager"
DEFAULT_SHARED_ROOT = "/opt/IBM/IMShared"
DEFAULT_MEDIA_ROOT = "/was855"
DEFAULT_PROFILE_NAME = "Dmgr01"


def common_wsadmin_argument_spec():
    return {
        "install_root": {"type": "path", "default": DEFAULT_INSTALL_ROOT},
        "profile_name": {"type": "str", "default": DEFAULT_PROFILE_NAME},
        "wsadmin_path": {"type": "path"},
        "username": {"type": "str", "required": True},
        "password": {"type": "str", "required": True, "no_log": True},
        "host": {"type": "str", "default": "localhost"},
        "port": {"type": "int", "default": 8879},
        "timeout": {"type": "int", "default": 300},
    }


def profile_root(install_root, profile_name):
    return os.path.join(install_root, "profiles", profile_name)


def replace_property(text, key, value):
    pattern = re.compile(r"(?m)^\s*%s\s*=.*$" % re.escape(key))
    line = "%s=%s" % (key, value)
    if pattern.search(text):
        return pattern.sub(line, text)
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n"


def redact(value, secrets):
    output = value or ""
    for secret in secrets:
        if secret:
            output = output.replace(secret, "********")
    return output


def run_checked(module, argv, cwd=None, environ_update=None, acceptable_rc=None):
    acceptable_rc = acceptable_rc or [0]
    rc, stdout, stderr = module.run_command(
        argv,
        cwd=cwd,
        environ_update=environ_update,
        check_rc=False,
    )
    secrets = [module.params.get("password"), module.params.get("admin_password")]
    stdout = redact(stdout, secrets)
    stderr = redact(stderr, secrets)
    if rc not in acceptable_rc:
        module.fail_json(
            msg="IBM command failed",
            command=argv[0],
            rc=rc,
            stdout=stdout,
            stderr=stderr,
        )
    return rc, stdout, stderr


def ensure_private_directory(path):
    if not os.path.isdir(path):
        os.makedirs(path, 0o700)
    os.chmod(path, 0o700)


@contextlib.contextmanager
def temporary_soap_properties(module, source_path, install_root, profile_name, persist=False):
    """Create a protected encoded SOAP client properties file.

    When persist is true, source_path itself is modified and an original copy is
    retained next to it for a later explicit restore. Normal wsadmin operations
    always use a short-lived copy.
    """
    if not os.path.isfile(source_path):
        module.fail_json(msg="SOAP client properties file is missing", path=source_path)

    backup_path = source_path + ".waslab.wasnd.original"
    temp_root = tempfile.mkdtemp(prefix="waslab-soap-", dir=module.tmpdir)
    generated_path = source_path if persist else os.path.join(temp_root, "soap.client.props")
    try:
        if persist and not os.path.exists(backup_path):
            shutil.copy2(source_path, backup_path)
            os.chmod(backup_path, 0o600)
        if not persist:
            shutil.copy2(source_path, generated_path)

        with open(generated_path, "r") as stream:
            properties = stream.read()
        properties = replace_property(properties, "com.ibm.SOAP.securityEnabled", "true")
        properties = replace_property(properties, "com.ibm.SOAP.loginSource", "none")
        properties = replace_property(properties, "com.ibm.SOAP.loginUserid", module.params["username"])
        properties = replace_property(properties, "com.ibm.SOAP.loginPassword", module.params["password"])
        with open(generated_path, "w") as stream:
            stream.write(properties)
        os.chmod(generated_path, 0o600)

        encoder = os.path.join(install_root, "bin", "PropFilePasswordEncoder.sh")
        if not os.access(encoder, os.X_OK):
            module.fail_json(msg="PropFilePasswordEncoder.sh is missing or not executable", path=encoder)
        run_checked(
            module,
            [encoder, generated_path, "com.ibm.SOAP.loginPassword", "-noBackup", "-profileName", profile_name],
        )
        yield generated_path
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@contextlib.contextmanager
def temporary_in_place_client_credentials(
    module,
    source_path,
    install_root,
    profile_name,
    connector,
):
    """Temporarily encode credentials in one client properties file."""
    if not os.path.isfile(source_path):
        module.fail_json(
            msg="%s client properties file is missing" % connector,
            path=source_path,
        )
    temp_root = tempfile.mkdtemp(prefix="waslab-soap-backup-", dir=module.tmpdir)
    backup_path = os.path.join(temp_root, os.path.basename(source_path))
    property_prefix = "com.ibm.%s" % connector
    shutil.copy2(source_path, backup_path)
    try:
        with open(source_path, "r") as stream:
            properties = stream.read()
        properties = replace_property(properties, property_prefix + ".securityEnabled", "true")
        # Native lifecycle tools such as serverStatus.sh and stopServer.sh read
        # credentials from the profile properties only when this source is
        # explicit.  The password is encoded below before the tool is invoked.
        properties = replace_property(properties, property_prefix + ".loginSource", "properties")
        properties = replace_property(
            properties,
            property_prefix + ".loginUserid",
            module.params["username"],
        )
        properties = replace_property(
            properties,
            property_prefix + ".loginPassword",
            module.params["password"],
        )
        with open(source_path, "w") as stream:
            stream.write(properties)
        os.chmod(source_path, 0o600)
        encoder = os.path.join(install_root, "bin", "PropFilePasswordEncoder.sh")
        run_checked(
            module,
            [
                encoder,
                source_path,
                property_prefix + ".loginPassword",
                "-noBackup",
                "-profileName",
                profile_name,
            ],
        )
        yield source_path
    finally:
        shutil.copy2(backup_path, source_path)
        shutil.rmtree(temp_root, ignore_errors=True)


@contextlib.contextmanager
def temporary_in_place_soap_credentials(module, source_path, install_root, profile_name):
    """Temporarily encode SOAP credentials, then restore the properties file."""
    with temporary_in_place_client_credentials(
        module,
        source_path,
        install_root,
        profile_name,
        "SOAP",
    ) as generated_path:
        yield generated_path


@contextlib.contextmanager
def temporary_in_place_ipc_credentials(module, source_path, install_root, profile_name):
    """Temporarily encode IPC credentials, then restore the properties file."""
    with temporary_in_place_client_credentials(
        module,
        source_path,
        install_root,
        profile_name,
        "IPC",
    ) as generated_path:
        yield generated_path


def restore_persisted_soap_properties(source_path):
    backup_path = source_path + ".waslab.wasnd.original"
    if not os.path.exists(backup_path):
        return False
    shutil.copy2(backup_path, source_path)
    os.chmod(source_path, stat.S_IRUSR | stat.S_IWUSR)
    os.remove(backup_path)
    return True


def require_destructive(module):
    if not module.params.get("allow_destructive", False):
        module.fail_json(
            msg="This removal is guarded. Set allow_destructive=true to authorize it explicitly."
        )
