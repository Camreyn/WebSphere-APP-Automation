#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: soap_credentials
short_description: Manage profile-local encoded SOAP credentials
version_added: "0.1.0"
description:
  - Persists IBM-encoded SOAP credentials for unattended profile scripts such as systemd ExecStop.
  - The original properties file is retained and restored when state is absent.
options:
  install_root:
    description: Traditional WebSphere installation root.
    type: path
    default: /opt/WebSphere/AppServers
  profile_name:
    description: Profile whose SOAP client properties are managed.
    type: str
    required: true
  username:
    description: WebSphere administrative user.
    type: str
    required: true
  password:
    description: WebSphere administrative password.
    type: str
    required: true
  state:
    description: Whether encoded credentials are persisted or the original file is restored.
    choices: [present, absent]
    type: str
    default: present
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Allow unattended stopManager.sh
  waslab.wasnd.soap_credentials:
    profile_name: Dmgr01
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
path:
  description: SOAP properties file that was managed.
  returned: always
  type: str
'''

import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    DEFAULT_INSTALL_ROOT,
    profile_root,
    restore_persisted_soap_properties,
    temporary_soap_properties,
)


def main():
    module = AnsibleModule(argument_spec={
        "install_root": {"type": "path", "default": DEFAULT_INSTALL_ROOT},
        "profile_name": {"type": "str", "required": True},
        "username": {"type": "str", "required": True},
        "password": {"type": "str", "required": True, "no_log": True},
        "state": {"type": "str", "choices": ["present", "absent"], "default": "present"},
    }, supports_check_mode=True)
    properties = os.path.join(
        profile_root(module.params["install_root"], module.params["profile_name"]),
        "properties", "soap.client.props",
    )
    backup = properties + ".waslab.wasnd.original"
    if module.params["state"] == "present":
        changed = not os.path.exists(backup)
        if changed and not module.check_mode:
            with temporary_soap_properties(
                module,
                properties,
                module.params["install_root"],
                module.params["profile_name"],
                persist=True,
            ):
                pass
    else:
        changed = os.path.exists(backup)
        if changed and not module.check_mode:
            restore_persisted_soap_properties(properties)
    module.exit_json(changed=changed, path=properties, state=module.params["state"])


if __name__ == "__main__":
    main()
