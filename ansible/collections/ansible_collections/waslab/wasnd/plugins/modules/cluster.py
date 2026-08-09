#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster
short_description: Manage a traditional WebSphere ND cluster
version_added: "0.1.0"
description: Creates, removes, starts, or stops a cluster through genuine wsadmin.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  name:
    description: Cluster name.
    type: str
    required: true
  state:
    description: Desired configuration or runtime state.
    choices: [present, absent, started, stopped]
    default: present
    type: str
  prefer_local:
    description: Prefer local EJB calls for a newly created cluster.
    type: bool
    default: true
  allow_destructive:
    description: Explicitly authorize cluster removal.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Start the application cluster
  waslab.wasnd.cluster:
    name: AppCluster01
    state: started
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
before:
  description: State observed before the operation.
  returned: always
  type: dict
after:
  description: State observed or predicted after the operation.
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    common_wsadmin_argument_spec,
    require_destructive,
)
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import exit_operation


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "name": {"type": "str", "required": True},
        "state": {"type": "str", "choices": ["present", "absent", "started", "stopped"], "default": "present"},
        "prefer_local": {"type": "bool", "default": True},
        "allow_destructive": {"type": "bool", "default": False},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params["state"] == "absent":
        require_destructive(module)
    exit_operation(module, BRIDGE, "cluster", {
        "name": module.params["name"],
        "state": module.params["state"],
        "prefer_local": module.params["prefer_local"],
        "check_mode": module.check_mode,
    })


if __name__ == "__main__":
    main()
