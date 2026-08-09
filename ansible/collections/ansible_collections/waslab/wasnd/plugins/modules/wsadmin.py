#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: wsadmin
short_description: Run a Jython file through genuine WebSphere wsadmin
version_added: "0.1.0"
description:
  - Runs caller-supplied Jython through the selected profile wsadmin.sh.
  - Controller-local files are read by the matching action plugin.
  - Scripts can return structured data with an ANSIBLE_WAS_RESULT JSON marker.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  src:
    description: Jython file on the controller, or on the managed host when remote_src is true.
    type: path
    required: true
  remote_src:
    description: Treat src as a path already on the managed host.
    type: bool
    default: false
  args:
    description: Positional arguments passed after the script path.
    type: list
    elements: str
    default: []
  changed:
    description: Fallback changed value when the script does not return structured JSON.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Run a custom controller-side Jython script
  waslab.wasnd.wsadmin:
    src: files/report.py
    args: [AppCluster01]
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
result:
  description: Structured dictionary emitted by the script, when present.
  returned: when provided by the script
  type: dict
stdout_lines:
  description: Sanitized wsadmin output.
  returned: always
  type: list
  elements: str
'''

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import RESULT_PREFIX, run_wsadmin_script


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "src": {"type": "path", "required": True},
        "remote_src": {"type": "bool", "default": False},
        "args": {"type": "list", "elements": "str", "default": []},
        "changed": {"type": "bool", "default": False},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=False)
    response = run_wsadmin_script(
        module,
        script_path=module.params["src"],
        args=module.params["args"],
    )
    structured = response.get("result")
    changed = module.params["changed"]
    if isinstance(structured, dict) and "changed" in structured:
        changed = bool(structured["changed"])
    module.exit_json(
        changed=changed,
        result=structured,
        rc=response["rc"],
        stdout=response["stdout"],
        stdout_lines=[line for line in response["stdout_lines"] if not line.startswith(RESULT_PREFIX)],
        stderr=response["stderr"],
    )


if __name__ == "__main__":
    main()
