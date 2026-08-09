#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: cell_info
short_description: Gather traditional WebSphere Base or ND cell information
version_added: "0.1.0"
description: Returns structured cell, cluster, member, application, and product information.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Read cell information
  waslab.wasnd.cell_info:
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
  register: was_cell
'''

RETURN = r'''
facts:
  description: Structured WebSphere cell information.
  returned: always
  type: dict
'''

import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec, run_checked
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import run_wsadmin_operation


def main():
    module = AnsibleModule(argument_spec=common_wsadmin_argument_spec(), supports_check_mode=True)
    version_info = module.params["install_root"] + "/bin/versionInfo.sh"
    unused_rc, stdout, unused_stderr = run_checked(module, [version_info, "-ifixes"])
    version_matches = re.findall(r"(?im)^\s*Version\s+([0-9][^\s]*)", stdout)
    response = run_wsadmin_operation(module, BRIDGE, "info", {})
    result = response.get("result")
    if result is None:
        module.fail_json(msg="wsadmin did not return cell information", stdout=response["stdout"])
    if "Network Deployment" in stdout or re.search(r"(?im)^\s*ID\s+ND\s*$", stdout):
        edition = "Network Deployment"
    elif re.search(r"(?im)^\s*ID\s+BASE\s*$", stdout) or "com.ibm.websphere.ILAN.v90" in stdout:
        edition = "Base"
    else:
        edition = "unknown"
    result["facts"]["product"] = {
        "edition": edition,
        # versionInfo lists Java before WebSphere; the WebSphere product is last.
        "version": version_matches[-1] if version_matches else "unknown",
    }
    result["wsadmin"] = {
        "rc": response["rc"],
        "stdout_lines": [line for line in response["stdout_lines"] if not line.startswith("ANSIBLE_WAS_RESULT=")],
    }
    module.exit_json(**result)


if __name__ == "__main__":
    main()
