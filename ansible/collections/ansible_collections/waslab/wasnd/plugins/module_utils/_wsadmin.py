# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type

import os
import shutil
import tempfile

from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    profile_root,
    redact,
    run_checked,
    temporary_soap_properties,
)
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin_codec import (
    jython21_literal,
    parse_wsadmin_result,
)


RESULT_PREFIX = "ANSIBLE_WAS_RESULT="
ERROR_PREFIX = "ANSIBLE_WAS_ERROR="


def _write_private(path, value, binary=False):
    mode = "wb" if binary else "w"
    with open(path, mode) as stream:
        stream.write(value)
    os.chmod(path, 0o600)


def run_wsadmin_script(module, script_content=None, script_path=None, args=None):
    install_root = module.params["install_root"]
    profile_name = module.params["profile_name"]
    root = profile_root(install_root, profile_name)
    wsadmin = module.params.get("wsadmin_path") or os.path.join(root, "bin", "wsadmin.sh")
    soap_source = os.path.join(root, "properties", "soap.client.props")
    if not os.access(wsadmin, os.X_OK):
        module.fail_json(msg="Genuine profile wsadmin.sh is missing or not executable", path=wsadmin)

    workdir = tempfile.mkdtemp(prefix="waslab-wsadmin-", dir=module.tmpdir)
    try:
        if script_content is not None:
            remote_script = os.path.join(workdir, "automation.py")
            _write_private(remote_script, script_content)
        else:
            if not script_path or not os.path.isfile(script_path):
                module.fail_json(msg="The requested Jython script does not exist", path=script_path)
            remote_script = script_path

        with temporary_soap_properties(module, soap_source, install_root, profile_name) as properties:
            argv = [
                wsadmin,
                "-lang", "jython",
                "-conntype", "SOAP",
                "-host", module.params["host"],
                "-port", str(module.params["port"]),
                "-javaoption", "-Dcom.ibm.SOAP.ConfigURL=file:%s" % properties,
                "-f", remote_script,
            ] + list(args or [])
            rc, stdout, stderr = run_checked(module, argv)

        result = None
        for line in stdout.splitlines():
            if line.startswith(ERROR_PREFIX):
                module.fail_json(
                    msg=line[len(ERROR_PREFIX):],
                    rc=rc,
                    stdout=redact(stdout, [module.params["password"]]),
                    stderr=redact(stderr, [module.params["password"]]),
                )
            if line.startswith(RESULT_PREFIX):
                try:
                    result = parse_wsadmin_result(line[len(RESULT_PREFIX):])
                except ValueError as exc:
                    module.fail_json(
                        msg="wsadmin returned an invalid collection result",
                        error=str(exc),
                        stdout=stdout,
                    )

        return {
            "rc": rc,
            "stdout": stdout,
            "stdout_lines": stdout.splitlines(),
            "stderr": stderr,
            "result": result,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def run_wsadmin_operation(module, bridge, operation, payload):
    workdir = tempfile.mkdtemp(prefix="waslab-payload-", dir=module.tmpdir)
    try:
        payload_path = os.path.join(workdir, "payload.literal")
        _write_private(payload_path, jython21_literal(payload))
        return run_wsadmin_script(
            module,
            script_content=bridge,
            args=[operation, payload_path],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def exit_operation(module, bridge, operation, payload):
    response = run_wsadmin_operation(module, bridge, operation, payload)
    result = response.get("result")
    if result is None:
        module.fail_json(
            msg="wsadmin completed without returning the collection result marker",
            stdout=response["stdout"],
            stderr=response["stderr"],
        )
    result["wsadmin"] = {
        "rc": response["rc"],
        "stdout_lines": [
            line for line in response["stdout_lines"]
            if not line.startswith(RESULT_PREFIX)
        ],
    }
    module.exit_json(**result)
