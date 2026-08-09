#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: profile
short_description: Manage traditional WebSphere profiles
version_added: "0.1.0"
description: Creates, backs up, and guardedly removes profiles with IBM manageprofiles.sh.
options:
  state:
    description: Whether the profile exists.
    choices: [present, absent]
    type: str
    default: present
  install_root:
    description: Traditional WebSphere installation root.
    type: path
    default: /opt/WebSphere/AppServers
  profile_name:
    description: Registered profile name.
    type: str
    required: true
  profile_path:
    description: Profile filesystem path; defaults below the installation profiles directory.
    type: path
  profile_type:
    description: WebSphere profile template to use.
    choices: [dmgr, managed, application_server]
    type: str
    required: true
  node_name:
    description: WebSphere node name.
    type: str
    required: true
  cell_name:
    description: Cell name, required for a deployment manager profile.
    type: str
  host_name:
    description: Host name recorded in the profile.
    type: str
  server_name:
    description: Server name for application-server profiles.
    type: str
    default: server1
  enable_admin_security:
    description: Enable administrative security when creating a deployment manager.
    type: bool
    default: true
  username:
    description: Initial or existing administrative user.
    type: str
    default: wsadmin
  password:
    description: Initial or existing administrative password.
    type: str
  default_ports:
    description: Ask manageprofiles to use the product default ports.
    type: bool
    default: true
  starting_port:
    description: First port in a generated profile port range.
    type: int
  ports_file:
    description: Managed-host path to an IBM profile ports file.
    type: path
  backup_dir:
    description: Protected directory for backups made before profile removal.
    type: path
    default: /var/backups/wasnd
  allow_destructive:
    description: Explicitly authorize profile backup and deletion.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Create a secured deployment manager profile
  become: true
  become_user: was
  waslab.wasnd.profile:
    profile_name: Dmgr01
    profile_type: dmgr
    profile_path: /opt/WebSphere/AppServers/profiles/Dmgr01
    node_name: DmgrNode01
    cell_name: LabCell01
    username: wsadmin
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
before:
  description: Profile state before the operation.
  returned: always
  type: dict
after:
  description: Profile state after the operation.
  returned: always
  type: dict
backup_file:
  description: Backup archive made before deletion.
  returned: when a profile is removed
  type: str
'''

import datetime
import os
import socket
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    DEFAULT_INSTALL_ROOT,
    ensure_private_directory,
    require_destructive,
    run_checked,
    temporary_in_place_soap_credentials,
)


def registered_path(module, manageprofiles):
    unused_rc, stdout, unused_stderr = run_checked(
        module,
        [manageprofiles, "-getPath", "-profileName", module.params["profile_name"]],
        acceptable_rc=[0, 1],
    )
    candidates = [line.strip() for line in stdout.splitlines() if line.strip().startswith("/")]
    return candidates[-1] if candidates else None


def write_response(module, profile_path):
    profile_type = module.params["profile_type"]
    templates = {
        "dmgr": "management",
        "managed": "managed",
        "application_server": "default",
    }
    lines = [
        "create",
        "profileName=%s" % module.params["profile_name"],
        "profilePath=%s" % profile_path,
        "templatePath=%s" % os.path.join(module.params["install_root"], "profileTemplates", templates[profile_type]),
        "nodeName=%s" % module.params["node_name"],
        "hostName=%s" % (module.params["host_name"] or socket.getfqdn()),
    ]
    if module.params.get("cell_name"):
        lines.append("cellName=%s" % module.params["cell_name"])
    if profile_type == "dmgr":
        lines.append("serverType=DEPLOYMENT_MANAGER")
        lines.append("enableAdminSecurity=%s" % str(module.params["enable_admin_security"]).lower())
        if module.params["enable_admin_security"]:
            if not module.params.get("password"):
                module.fail_json(msg="password is required when deployment-manager security is enabled")
            lines.extend([
                "adminUserName=%s" % module.params["username"],
                "adminPassword=%s" % module.params["password"],
            ])
    elif profile_type == "managed":
        lines.append("federateLater=true")
    else:
        lines.append("serverName=%s" % module.params["server_name"])

    if module.params.get("ports_file"):
        lines.append("portsFile=%s" % module.params["ports_file"])
    elif module.params.get("starting_port") is not None:
        lines.append("startingPort=%s" % module.params["starting_port"])
    elif module.params["default_ports"]:
        lines.append("defaultPorts=true")

    handle, path = tempfile.mkstemp(prefix="waslab-profile-", suffix=".rsp", dir=module.tmpdir)
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write("\n".join(lines) + "\n")
        os.chmod(path, 0o600)
    except Exception:
        os.unlink(path)
        raise
    return path


def stop_profile(module, profile_path):
    commands = {
        "dmgr": ([os.path.join(profile_path, "bin", "stopManager.sh")]),
        "managed": ([os.path.join(profile_path, "bin", "stopNode.sh")]),
        "application_server": ([os.path.join(profile_path, "bin", "stopServer.sh"), module.params["server_name"]]),
    }
    argv = commands[module.params["profile_type"]]
    if not os.access(argv[0], os.X_OK):
        return
    soap = os.path.join(profile_path, "properties", "soap.client.props")
    if module.params.get("password") and os.path.isfile(soap):
        with temporary_in_place_soap_credentials(
            module,
            soap,
            module.params["install_root"],
            module.params["profile_name"],
        ):
            run_checked(module, argv, acceptable_rc=[0, 1])
    else:
        run_checked(module, argv, acceptable_rc=[0, 1])


def main():
    module = AnsibleModule(argument_spec={
        "state": {"type": "str", "choices": ["present", "absent"], "default": "present"},
        "install_root": {"type": "path", "default": DEFAULT_INSTALL_ROOT},
        "profile_name": {"type": "str", "required": True},
        "profile_path": {"type": "path"},
        "profile_type": {"type": "str", "choices": ["dmgr", "managed", "application_server"], "required": True},
        "node_name": {"type": "str", "required": True},
        "cell_name": {"type": "str"},
        "host_name": {"type": "str"},
        "server_name": {"type": "str", "default": "server1"},
        "enable_admin_security": {"type": "bool", "default": True},
        "username": {"type": "str", "default": "wsadmin"},
        "password": {"type": "str", "no_log": True},
        "default_ports": {"type": "bool", "default": True},
        "starting_port": {"type": "int"},
        "ports_file": {"type": "path"},
        "backup_dir": {"type": "path", "default": "/var/backups/wasnd"},
        "allow_destructive": {"type": "bool", "default": False},
    }, mutually_exclusive=[["starting_port", "ports_file"]], supports_check_mode=True)

    manageprofiles = os.path.join(module.params["install_root"], "bin", "manageprofiles.sh")
    if not os.access(manageprofiles, os.X_OK):
        module.fail_json(msg="manageprofiles.sh is missing or not executable", path=manageprofiles)
    expected_path = module.params["profile_path"] or os.path.join(
        module.params["install_root"], "profiles", module.params["profile_name"]
    )
    current_path = registered_path(module, manageprofiles)
    before = {"exists": bool(current_path), "path": current_path}

    if module.params["state"] == "present":
        if current_path:
            if os.path.realpath(current_path) != os.path.realpath(expected_path):
                module.fail_json(
                    msg="Registered profile path differs from requested path",
                    profile_name=module.params["profile_name"],
                    registered_path=current_path,
                    requested_path=expected_path,
                )
            module.exit_json(changed=False, before=before, after=before)
        if module.params["profile_type"] == "dmgr" and not module.params.get("cell_name"):
            module.fail_json(msg="cell_name is required for a deployment-manager profile")
        if not module.check_mode:
            response = write_response(module, expected_path)
            try:
                run_checked(module, [manageprofiles, "-response", response])
            finally:
                if os.path.exists(response):
                    os.remove(response)
        module.exit_json(
            changed=True,
            before=before,
            after={"exists": True, "path": expected_path},
        )

    require_destructive(module)
    if not current_path:
        module.exit_json(changed=False, before=before, after=before)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_file = os.path.join(
        module.params["backup_dir"],
        "%s-%s.zip" % (module.params["profile_name"], timestamp),
    )
    if not module.check_mode:
        stop_profile(module, current_path)
        ensure_private_directory(module.params["backup_dir"])
        run_checked(module, [
            manageprofiles,
            "-backupProfile",
            "-profileName", module.params["profile_name"],
            "-backupFile", backup_file,
        ])
        run_checked(module, [manageprofiles, "-delete", "-profileName", module.params["profile_name"]])
    module.exit_json(
        changed=True,
        before=before,
        after={"exists": False, "path": None},
        backup_file=backup_file,
    )


if __name__ == "__main__":
    main()
