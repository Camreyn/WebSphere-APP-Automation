#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: jvm_heap
short_description: Configure WebSphere cluster-member JVM heap sizes
version_added: "0.1.0"
description: Idempotently sets initial and maximum JVM heap values through genuine wsadmin.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  cluster:
    description: Cluster whose members are changed.
    type: str
    required: true
  initial_heap_mb:
    description: Initial heap in MiB.
    type: int
    required: true
  maximum_heap_mb:
    description: Maximum heap in MiB.
    type: int
    required: true
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Configure heap
  waslab.wasnd.jvm_heap:
    cluster: AppCluster01
    initial_heap_mb: 256
    maximum_heap_mb: 768
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
members:
  description: Heap comparison for every cluster member.
  returned: always
  type: list
  elements: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import exit_operation


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "cluster": {"type": "str", "required": True},
        "initial_heap_mb": {"type": "int", "required": True},
        "maximum_heap_mb": {"type": "int", "required": True},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    if module.params["initial_heap_mb"] > module.params["maximum_heap_mb"]:
        module.fail_json(msg="initial_heap_mb cannot exceed maximum_heap_mb")
    exit_operation(module, BRIDGE, "jvm_heap", {
        "cluster": module.params["cluster"],
        "initial_heap_mb": module.params["initial_heap_mb"],
        "maximum_heap_mb": module.params["maximum_heap_mb"],
        "check_mode": module.check_mode,
    })


if __name__ == "__main__":
    main()
