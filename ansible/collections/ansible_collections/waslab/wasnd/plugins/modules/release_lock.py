#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: release_lock
short_description: Serialize WebSphere application deployments
version_added: "0.1.0"
description:
  - Uses an atomic managed-host directory to prevent concurrent deployment jobs.
  - Records protected owner and request metadata and identifies stale locks.
options:
  name:
    description: Lock name, normally the WebSphere application name.
    type: str
    required: true
  state:
    description: Desired lock operation.
    choices: [acquired, released, status]
    type: str
    default: acquired
  owner:
    description: Unique job owner used to acquire and release the lock.
    type: str
  lock_root:
    description: Private parent directory for application locks.
    type: path
    default: /var/tmp/waslab-locks
  metadata:
    description: Non-secret request metadata stored with a newly acquired lock.
    type: dict
    default: {}
  stale_after:
    description: Age in seconds after which a lock is reported as stale.
    type: int
    default: 14400
  break_stale:
    description: Replace an existing lock only when it is stale.
    type: bool
    default: false
  force_release:
    description: Release a lock owned by another job.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Acquire a deployment lock
  waslab.wasnd.release_lock:
    name: PayrollApplication
    owner: "awx-{{ awx_job_id }}"
    state: acquired

- name: Release the deployment lock
  waslab.wasnd.release_lock:
    name: PayrollApplication
    owner: "awx-{{ awx_job_id }}"
    state: released
'''

RETURN = r'''
locked:
  description: Whether the lock exists after the operation.
  returned: always
  type: bool
lock:
  description: Stored lock metadata.
  returned: when a lock exists
  type: dict
age_seconds:
  description: Current lock age.
  returned: when a lock exists
  type: int
stale:
  description: Whether the lock exceeds stale_after.
  returned: when a lock exists
  type: bool
'''

import datetime
import json
import os
import re
import shutil
import socket
import time

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import ensure_private_directory


NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def read_lock(path):
    metadata_path = os.path.join(path, "owner.json")
    try:
        with open(metadata_path, "r") as stream:
            value = json.load(stream)
        return value if isinstance(value, dict) else {}
    except (IOError, ValueError):
        return {}


def lock_status(path, stale_after):
    if not os.path.isdir(path):
        return {"locked": False, "lock": None, "age_seconds": None, "stale": False}
    value = read_lock(path)
    created_epoch = value.get("acquired_epoch", os.path.getmtime(path))
    try:
        age = max(0, int(time.time() - float(created_epoch)))
    except (TypeError, ValueError):
        age = max(0, int(time.time() - os.path.getmtime(path)))
    return {
        "locked": True,
        "lock": value,
        "age_seconds": age,
        "stale": age >= stale_after,
    }


def main():
    module = AnsibleModule(
        argument_spec={
            "name": {"type": "str", "required": True},
            "state": {
                "type": "str",
                "choices": ["acquired", "released", "status"],
                "default": "acquired",
            },
            "owner": {"type": "str"},
            "lock_root": {"type": "path", "default": "/var/tmp/waslab-locks"},
            "metadata": {"type": "dict", "default": {}},
            "stale_after": {"type": "int", "default": 14400},
            "break_stale": {"type": "bool", "default": False},
            "force_release": {"type": "bool", "default": False},
        },
        required_if=[
            ["state", "acquired", ["owner"]],
            ["state", "released", ["owner"]],
        ],
        supports_check_mode=True,
    )
    name = module.params["name"]
    if not NAME_PATTERN.match(name):
        module.fail_json(msg="Lock name contains unsupported characters", name=name)
    if module.params["stale_after"] < 60:
        module.fail_json(msg="stale_after must be at least 60 seconds")

    root = os.path.realpath(module.params["lock_root"])
    path = os.path.join(root, name + ".lock")
    state = module.params["state"]
    before = lock_status(path, module.params["stale_after"])
    if state == "status":
        module.exit_json(changed=False, path=path, **before)

    if state == "acquired":
        if before["locked"] and not (
                before["stale"] and module.params["break_stale"]):
            module.fail_json(
                msg="Another deployment owns the application lock",
                path=path,
                lock=before["lock"],
                age_seconds=before["age_seconds"],
                stale=before["stale"],
            )
        if module.check_mode:
            module.exit_json(
                changed=True,
                path=path,
                locked=True,
                lock={"owner": module.params["owner"], **module.params["metadata"]},
                age_seconds=0,
                stale=False,
            )
        ensure_private_directory(root)
        if before["locked"]:
            shutil.rmtree(path)
        try:
            os.mkdir(path, 0o700)
        except OSError as exc:
            current = lock_status(path, module.params["stale_after"])
            module.fail_json(
                msg="Unable to atomically acquire the application lock",
                error=str(exc),
                lock=current.get("lock"),
            )
        now = time.time()
        lock = {
            "owner": module.params["owner"],
            "application": name,
            "acquired_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "acquired_epoch": now,
            "host": socket.getfqdn(),
            "pid": os.getpid(),
            "request": module.params["metadata"],
        }
        metadata_path = os.path.join(path, "owner.json")
        with open(metadata_path, "w") as stream:
            json.dump(lock, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(metadata_path, 0o600)
        module.exit_json(
            changed=True,
            path=path,
            locked=True,
            lock=lock,
            age_seconds=0,
            stale=False,
        )

    if not before["locked"]:
        module.exit_json(changed=False, path=path, **before)
    current_owner = (before["lock"] or {}).get("owner")
    if current_owner != module.params["owner"] and not module.params["force_release"]:
        module.fail_json(
            msg="Refusing to release a lock owned by another job",
            requested_owner=module.params["owner"],
            current_owner=current_owner,
            lock=before["lock"],
        )
    if module.check_mode:
        module.exit_json(
            changed=True,
            path=path,
            locked=False,
            lock=None,
            age_seconds=None,
            stale=False,
        )
    shutil.rmtree(path)
    module.exit_json(
        changed=True,
        path=path,
        locked=False,
        lock=None,
        age_seconds=None,
        stale=False,
    )


if __name__ == "__main__":
    main()
