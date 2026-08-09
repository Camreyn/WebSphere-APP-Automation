#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: release_record
short_description: Record WebSphere application release history
version_added: "0.1.0"
description:
  - Maintains a protected atomic record of current and previous application releases.
  - Supplies a known-good immutable artifact path for automated rollback.
options:
  application:
    description: WebSphere application name.
    type: str
    required: true
  operation:
    description: Read state or promote a successfully validated release.
    choices: [get, record]
    type: str
    default: get
  release:
    description: Release metadata to promote when state is record.
    type: dict
  path:
    description: Protected deployment-history JSON path.
    type: path
    default: /var/lib/waslab/wasnd/deployment-history.json
  max_history:
    description: Maximum prior releases retained per application.
    type: int
    default: 20
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Read the current and previous release
  waslab.wasnd.release_record:
    application: PayrollApplication
    operation: get

- name: Promote a successful release
  waslab.wasnd.release_record:
    application: PayrollApplication
    operation: record
    release:
      version: 2026.08.08.3
      checksum: 1d79...
      artifact_path: /mnt/releases/payroll/2026.08.08.3/payroll.ear
'''

RETURN = r'''
current:
  description: Current successful release metadata.
  returned: always
  type: dict
previous:
  description: Most recently replaced release metadata.
  returned: always
  type: dict
history:
  description: Prior successful releases, newest first.
  returned: always
  type: list
  elements: dict
'''

import json
import os
import re

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import ensure_private_directory


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def read_database(path):
    if not os.path.isfile(path):
        return {"schema": 1, "applications": {}}
    try:
        with open(path, "r") as stream:
            value = json.load(stream)
        if not isinstance(value, dict) or not isinstance(value.get("applications"), dict):
            raise ValueError("root applications object is missing")
        return value
    except (IOError, ValueError) as exc:
        raise ValueError("Deployment-history file is invalid: %s" % exc)


def release_key(value):
    if not isinstance(value, dict):
        return None
    return (value.get("version"), value.get("checksum"), value.get("artifact_path"))


def main():
    module = AnsibleModule(
        argument_spec={
            "application": {"type": "str", "required": True},
            "operation": {"type": "str", "choices": ["get", "record"], "default": "get"},
            "release": {"type": "dict"},
            "path": {
                "type": "path",
                "default": "/var/lib/waslab/wasnd/deployment-history.json",
            },
            "max_history": {"type": "int", "default": 20},
        },
        required_if=[["operation", "record", ["release"]]],
        supports_check_mode=True,
    )
    if module.params["max_history"] < 1:
        module.fail_json(msg="max_history must be at least one")
    path = module.params["path"]
    try:
        database = read_database(path)
    except ValueError as exc:
        module.fail_json(msg=str(exc), path=path)
    application = module.params["application"]
    application_state = database["applications"].get(
        application,
        {"current": None, "history": []},
    )
    current = application_state.get("current")
    history = application_state.get("history") or []
    if module.params["operation"] == "get":
        module.exit_json(
            changed=False,
            path=path,
            current=current,
            previous=history[0] if history else None,
            history=history,
        )

    release = dict(module.params["release"])
    missing = [key for key in ("version", "checksum", "artifact_path") if not release.get(key)]
    if missing:
        module.fail_json(msg="Release metadata is missing required fields", missing=missing)
    if not SHA256_PATTERN.match(str(release["checksum"])):
        module.fail_json(msg="Release checksum must be a SHA-256 value")
    release["checksum"] = str(release["checksum"]).lower()
    changed = release_key(current) != release_key(release)
    if not changed:
        module.exit_json(
            changed=False,
            path=path,
            current=current,
            previous=history[0] if history else None,
            history=history,
        )

    new_history = list(history)
    if current and release_key(current) not in [release_key(item) for item in new_history]:
        new_history.insert(0, current)
    new_history = [item for item in new_history if release_key(item) != release_key(release)]
    new_history = new_history[:module.params["max_history"]]
    if not module.check_mode:
        database["applications"][application] = {
            "current": release,
            "history": new_history,
        }
        parent = os.path.dirname(path) or "."
        ensure_private_directory(parent)
        temporary = path + ".tmp"
        with open(temporary, "w") as stream:
            json.dump(database, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.rename(temporary, path)
    module.exit_json(
        changed=True,
        path=path,
        current=release,
        previous=new_history[0] if new_history else None,
        history=new_history,
    )


if __name__ == "__main__":
    main()
