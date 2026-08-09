#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: application
short_description: Manage an application in traditional WebSphere Base or ND
version_added: "0.1.0"
description:
  - Installs, checksum-updates, removes, starts, or stops an enterprise application.
  - The archive path is on the managed Base or deployment-manager host.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  name:
    description: WebSphere application name.
    type: str
    required: true
  state:
    description: Desired configuration or runtime state.
    choices: [present, absent, started, stopped]
    type: str
    default: present
  src:
    description: Remote WAR or EAR path required for state present.
    type: path
  cluster:
    description: Target cluster for a new installation.
    type: str
  context_root:
    description: Context root for a new web application.
    type: str
  virtual_host:
    description:
      - Default virtual host binding used for web modules on a new installation.
      - Set an empty value only when the archive supplies all required bindings.
    type: str
    default: default_host
  force:
    description: Update an existing application even when its recorded checksum matches.
    type: bool
    default: false
  ledger_path:
    description: Protected remote checksum ledger used for idempotent updates.
    type: path
    default: /var/lib/waslab/wasnd/application-checksums.json
  allow_destructive:
    description: Explicitly authorize application removal.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Deploy a staged WAR
  waslab.wasnd.application:
    name: was-lab
    src: /var/tmp/was-lab.war
    cluster: AppCluster01
    context_root: /was-lab
    state: present
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
checksum:
  description: SHA-256 of the supplied archive.
  returned: when state is present
  type: str
before:
  description: State before the operation.
  returned: always
  type: dict
after:
  description: State after the operation.
  returned: always
  type: dict
'''

import hashlib
import json
import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import common_wsadmin_argument_spec, ensure_private_directory, require_destructive
from ansible_collections.waslab.wasnd.plugins.module_utils._jython import BRIDGE
from ansible_collections.waslab.wasnd.plugins.module_utils._wsadmin import run_wsadmin_operation


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_ledger(path):
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (IOError, ValueError):
        return {}


def write_ledger(path, value):
    ensure_private_directory(os.path.dirname(path))
    temporary = path + ".tmp"
    with open(temporary, "w") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
    os.chmod(temporary, 0o600)
    os.rename(temporary, path)


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "name": {"type": "str", "required": True},
        "state": {"type": "str", "choices": ["present", "absent", "started", "stopped"], "default": "present"},
        "src": {"type": "path"},
        "cluster": {"type": "str"},
        "context_root": {"type": "str"},
        "virtual_host": {"type": "str", "default": "default_host"},
        "force": {"type": "bool", "default": False},
        "ledger_path": {"type": "path", "default": "/var/lib/waslab/wasnd/application-checksums.json"},
        "allow_destructive": {"type": "bool", "default": False},
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    state = module.params["state"]
    if state == "absent":
        require_destructive(module)
    if state == "present" and not module.params["src"]:
        module.fail_json(msg="src is required when state=present")
    if state == "present" and not os.path.isfile(module.params["src"]):
        module.fail_json(msg="Application archive does not exist on the managed host", path=module.params["src"])

    ledger = read_ledger(module.params["ledger_path"])
    checksum = file_sha256(module.params["src"]) if state == "present" else None
    update = state == "present" and (module.params["force"] or ledger.get(module.params["name"]) != checksum)
    response = run_wsadmin_operation(module, BRIDGE, "application", {
        "name": module.params["name"],
        "state": state,
        "archive": module.params["src"],
        "cluster": module.params["cluster"],
        "context_root": module.params["context_root"],
        "virtual_host": module.params["virtual_host"],
        "update": update,
        "check_mode": module.check_mode,
    })
    result = response.get("result")
    if result is None:
        module.fail_json(msg="wsadmin did not return application state", stdout=response["stdout"])

    if not module.check_mode:
        if state == "present" and result.get("after", {}).get("installed"):
            ledger[module.params["name"]] = checksum
            write_ledger(module.params["ledger_path"], ledger)
        elif state == "absent" and module.params["name"] in ledger:
            del ledger[module.params["name"]]
            write_ledger(module.params["ledger_path"], ledger)
    if checksum:
        result["checksum"] = checksum
    result["wsadmin"] = {
        "rc": response["rc"],
        "stdout_lines": [line for line in response["stdout_lines"] if not line.startswith("ANSIBLE_WAS_RESULT=")],
    }
    module.exit_json(**result)


if __name__ == "__main__":
    main()
