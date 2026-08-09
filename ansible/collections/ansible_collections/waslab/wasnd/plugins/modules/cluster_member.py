#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cluster_member
short_description: Manage a traditional WebSphere ND cluster member
version_added: "0.1.0"
description: Creates, removes, starts, stops, or restarts one ND cluster member.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  cluster:
    description: Parent cluster name.
    type: str
    required: true
  node:
    description: Federated node name.
    type: str
    required: true
  name:
    description: Cluster member server name.
    type: str
    default: server1
  state:
    description: Desired configuration or runtime state.
    choices: [present, absent, started, stopped, restarted]
    default: present
    type: str
  weight:
    description: Initial cluster routing weight.
    type: int
    default: 2
  generate_unique_ports:
    description: Ask WebSphere to generate unique ports for the member.
    type: bool
    default: false
  allow_destructive:
    description: Explicitly authorize member removal.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Ensure Node01 is a cluster member
  waslab.wasnd.cluster_member:
    cluster: AppCluster01
    node: Node01
    name: server1
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
before:
  description: State before the operation.
  returned: always
  type: dict
after:
  description: State after the operation.
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec, require_destructive
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import exit_operation


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "cluster": {"type": "str", "required": True},
        "node": {"type": "str", "required": True},
        "name": {"type": "str", "default": "server1"},
        "state": {"type": "str", "choices": ["present", "absent", "started", "stopped", "restarted"], "default": "present"},
        "weight": {"type": "int", "default": 2},
        "generate_unique_ports": {"type": "bool", "default": False},
        "allow_destructive": {"type": "bool", "default": False},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params["state"] == "absent":
        require_destructive(module)
    exit_operation(module, BRIDGE, "cluster_member", {
        "cluster": module.params["cluster"],
        "node": module.params["node"],
        "name": module.params["name"],
        "state": module.params["state"],
        "weight": module.params["weight"],
        "generate_unique_ports": module.params["generate_unique_ports"],
        "check_mode": module.check_mode,
    })


if __name__ == "__main__":
    main()
