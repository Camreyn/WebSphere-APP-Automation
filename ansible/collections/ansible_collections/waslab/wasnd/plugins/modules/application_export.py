#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: application_export
short_description: Export an installed traditional WebSphere application
version_added: "0.1.0"
description:
  - Uses C(AdminApp.export) to create a complete EAR backup before an update.
  - WebSphere exports preserve application binding information, making the
    resulting archive suitable for guarded automatic rollback.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  name:
    description: Installed WebSphere application name.
    type: str
    required: true
  dest:
    description: Destination EAR path on the managed WebSphere host.
    type: path
    required: true
  overwrite:
    description: Replace an existing backup path.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Export the current application before updating it
  waslab.wasnd.application_export:
    name: orders
    dest: /var/tmp/waslab-backups/orders/42/orders.ear
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
checksum:
  description: SHA-256 of the exported EAR.
  returned: when not in check mode
  type: str
size:
  description: Exported EAR size in bytes.
  returned: when not in check mode
  type: int
destination:
  description: Canonical backup path.
  returned: always
  type: str
'''

import hashlib
import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    common_wsadmin_argument_spec,
    ensure_private_directory,
)
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import run_wsadmin_operation


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "name": {"type": "str", "required": True},
        "dest": {"type": "path", "required": True},
        "overwrite": {"type": "bool", "default": False},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    destination = os.path.realpath(module.params["dest"])
    parent = os.path.dirname(destination)
    if os.path.exists(destination) and not module.params["overwrite"]:
        module.fail_json(msg="Application export destination already exists", destination=destination)
    if not module.check_mode:
        ensure_private_directory(parent)
        if os.path.exists(destination):
            os.remove(destination)

    response = run_wsadmin_operation(module, BRIDGE, "application_export", {
        "name": module.params["name"],
        "destination": destination,
        "check_mode": module.check_mode,
    })
    result = response.get("result")
    if result is None:
        module.fail_json(msg="wsadmin did not return application export state", stdout=response["stdout"])
    if not module.check_mode:
        if not os.path.isfile(destination):
            module.fail_json(msg="WebSphere reported a successful export but no EAR was created", destination=destination)
        result["checksum"] = file_sha256(destination)
        result["size"] = os.path.getsize(destination)
        os.chmod(destination, 0o600)
    result["wsadmin"] = {
        "rc": response["rc"],
        "stdout_lines": [
            line for line in response["stdout_lines"]
            if not line.startswith("ANSIBLE_WAS_RESULT=")
        ],
    }
    module.exit_json(**result)


if __name__ == "__main__":
    main()
