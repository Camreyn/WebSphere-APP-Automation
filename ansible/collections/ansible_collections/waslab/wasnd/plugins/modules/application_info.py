#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: application_info
short_description: Discover an installed traditional WebSphere application
version_added: "0.1.0"
description:
  - Reads an application's installed and runtime state from the live cell.
  - Returns module, target-mapping, context-root, and virtual-host information
    exposed by C(AdminApp), without requiring a source-controlled app catalog.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  name:
    description: WebSphere application name to discover.
    type: str
    required: true
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Discover the live application identity and mappings
  waslab.wasnd.application_info:
    name: orders
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
  register: orders_application
'''

RETURN = r'''
application:
  description: Live installed, runtime, module, and configuration information.
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import exit_operation


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({"name": {"type": "str", "required": True}})
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    exit_operation(module, BRIDGE, "application_info", {"name": module.params["name"]})


if __name__ == "__main__":
    main()
