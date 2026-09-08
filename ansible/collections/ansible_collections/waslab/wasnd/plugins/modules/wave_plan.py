#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: wave_plan
short_description: Build safe Node 2 then Node 1 waves from discovered WAS topology
version_added: "0.1.0"
description:
  - Correlates local managed-node and Dmgr profiles with live wsadmin cell data.
  - Identifies each two-host cell pair, places the non-Dmgr host in wave 1,
    and places the co-located Dmgr host in wave 2.
  - Fails before maintenance when topology is incomplete or ambiguous.
options:
  topologies:
    description: Mapping of inventory hostname to topology_info results.
    type: dict
    required: true
  cells:
    description: Mapping of Dmgr inventory hostname to live cell and application facts.
    type: dict
    required: true
  require_two_node_cells:
    description: Require exactly one Node 1/Node 2 pair in every discovered cell.
    type: bool
    default: true
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Assemble maintenance waves without per-host topology variables
  waslab.wasnd.wave_plan:
    topologies: "{{ discovered_topologies }}"
    cells: "{{ discovered_cells }}"
  register: maintenance_plan
'''

RETURN = r'''
plan:
  description: Host variables, wave membership, cell pairs, and recommended fork count.
  returned: always
  type: dict
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._wave_plan import (
    WavePlanError,
    build_wave_plan,
)


def main():
    module = AnsibleModule(
        argument_spec={
            "topologies": {"type": "dict", "required": True},
            "cells": {"type": "dict", "required": True},
            "require_two_node_cells": {"type": "bool", "default": True},
        },
        supports_check_mode=True,
    )
    try:
        plan = build_wave_plan(
            module.params["topologies"],
            module.params["cells"],
            module.params["require_two_node_cells"],
        )
        module.exit_json(changed=False, plan=plan)
    except WavePlanError as exc:
        module.fail_json(msg=str(exc))


if __name__ == "__main__":
    main()
