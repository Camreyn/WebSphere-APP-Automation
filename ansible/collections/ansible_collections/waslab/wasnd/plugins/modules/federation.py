#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: federation
short_description: Federate a traditional WebSphere managed profile
version_added: "0.1.0"
description:
  - Uses the managed profile addNode.sh or removeNode.sh command.
  - Credentials are temporarily encoded in profile SOAP properties and are not placed in process arguments.
options:
  state:
    description: Whether the node belongs to the deployment-manager cell.
    choices: [present, absent]
    type: str
    default: present
  install_root:
    description: Traditional WebSphere installation root.
    type: path
    default: /opt/WebSphere/AppServers
  profile_name:
    description: Managed profile name.
    type: str
    default: AppSrv01
  profile_path:
    description: Managed profile path; defaults below the installation profiles directory.
    type: path
  node_name:
    description: Node name expected in the deployment-manager cell.
    type: str
    required: true
  cell_name:
    description: Deployment-manager cell name.
    type: str
    required: true
  dmgr_host:
    description: Deployment manager hostname reachable from the node.
    type: str
    required: true
  dmgr_port:
    description: Deployment manager SOAP connector port.
    type: int
    default: 8879
  username:
    description: WebSphere administrative user.
    type: str
    required: true
  password:
    description: WebSphere administrative password.
    type: str
    required: true
  no_agent:
    description: Do not start the node agent automatically during federation.
    type: bool
    default: false
  allow_destructive:
    description: Explicitly authorize removing the node from its cell.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Federate Node01
  become: true
  become_user: was
  waslab.wasnd.federation:
    node_name: Node01
    cell_name: LabCell01
    dmgr_host: was-dmgr
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
before:
  description: Federation state before the operation.
  returned: always
  type: dict
after:
  description: Federation state after the operation.
  returned: always
  type: dict
'''

import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    DEFAULT_INSTALL_ROOT,
    require_destructive,
    run_checked,
    temporary_in_place_soap_credentials,
)


def is_federated(profile_path, cell_name, node_name):
    return os.path.isdir(os.path.join(
        profile_path, "config", "cells", cell_name, "nodes", node_name
    ))


def main():
    module = AnsibleModule(argument_spec={
        "state": {"type": "str", "choices": ["present", "absent"], "default": "present"},
        "install_root": {"type": "path", "default": DEFAULT_INSTALL_ROOT},
        "profile_name": {"type": "str", "default": "AppSrv01"},
        "profile_path": {"type": "path"},
        "node_name": {"type": "str", "required": True},
        "cell_name": {"type": "str", "required": True},
        "dmgr_host": {"type": "str", "required": True},
        "dmgr_port": {"type": "int", "default": 8879},
        "username": {"type": "str", "required": True},
        "password": {"type": "str", "required": True, "no_log": True},
        "no_agent": {"type": "bool", "default": False},
        "allow_destructive": {"type": "bool", "default": False},
    }, supports_check_mode=True)
    profile_path = module.params["profile_path"] or os.path.join(
        module.params["install_root"], "profiles", module.params["profile_name"]
    )
    if not os.path.isdir(profile_path):
        module.fail_json(msg="Managed profile path does not exist", path=profile_path)
    before_value = is_federated(profile_path, module.params["cell_name"], module.params["node_name"])
    before = {"federated": before_value, "cell": module.params["cell_name"], "node": module.params["node_name"]}
    wants_present = module.params["state"] == "present"
    if before_value == wants_present:
        module.exit_json(changed=False, before=before, after=before)
    if not wants_present:
        require_destructive(module)
    if module.check_mode:
        module.exit_json(
            changed=True,
            before=before,
            after={"federated": wants_present, "cell": module.params["cell_name"], "node": module.params["node_name"]},
        )

    properties = os.path.join(profile_path, "properties", "soap.client.props")
    command = os.path.join(profile_path, "bin", "addNode.sh" if wants_present else "removeNode.sh")
    if not os.access(command, os.X_OK):
        module.fail_json(msg="Required IBM federation command is unavailable", path=command)
    argv = [command]
    if wants_present:
        argv.extend([module.params["dmgr_host"], str(module.params["dmgr_port"])])
        if module.params["no_agent"]:
            argv.append("-noagent")
    with temporary_in_place_soap_credentials(
        module,
        properties,
        module.params["install_root"],
        module.params["profile_name"],
    ):
        unused_rc, stdout, stderr = run_checked(module, argv)

    after_value = is_federated(profile_path, module.params["cell_name"], module.params["node_name"])
    if after_value != wants_present:
        module.fail_json(
            msg="IBM federation command completed but the profile configuration has the wrong cell state",
            stdout=stdout,
            stderr=stderr,
            expected_federated=wants_present,
            detected_federated=after_value,
        )
    module.exit_json(
        changed=True,
        before=before,
        after={"federated": after_value, "cell": module.params["cell_name"], "node": module.params["node_name"]},
        stdout_lines=stdout.splitlines(),
    )


if __name__ == "__main__":
    main()
