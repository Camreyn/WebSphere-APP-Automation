#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: node_sync
short_description: Synchronize managed WebSphere nodes
version_added: "0.1.0"
description: Invokes NodeSync MBeans through genuine deployment-manager wsadmin.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  nodes:
    description: Node names to synchronize; an empty list selects every managed node.
    type: list
    elements: str
    default: []
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Synchronize Node01 and Node02
  waslab.wasnd.node_sync:
    nodes: [Node01, Node02]
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
synced:
  description: Nodes for which synchronization was invoked.
  returned: always
  type: list
  elements: dict
unavailable:
  description: Requested nodes without a runtime NodeSync MBean.
  returned: always
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import exit_operation


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({"nodes": {"type": "list", "elements": "str", "default": []}})
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    exit_operation(module, BRIDGE, "node_sync", {
        "nodes": module.params["nodes"],
        "check_mode": module.check_mode,
    })


if __name__ == "__main__":
    main()
