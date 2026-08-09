#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: profile_runtime
short_description: Manage a traditional WebSphere profile runtime
version_added: "0.1.0"
description:
  - Starts, stops, or restarts the native process associated with an existing
    traditional WebSphere profile.
  - Uses the profile's IBM lifecycle scripts and reports structured before and
    after state without passing the administrative password on the command line.
extends_documentation_fragment:
  - waslab.wasnd.was_connection
options:
  profile_type:
    description: Native process owned by the profile.
    choices: [dmgr, node, application_server]
    type: str
    required: true
  server_name:
    description: Server name used when C(profile_type=application_server).
    type: str
    default: server1
  state:
    description: Desired runtime state.
    choices: [started, stopped, restarted]
    type: str
    default: started
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Ensure a stand-alone application server is running
  become: true
  become_user: was
  waslab.wasnd.profile_runtime:
    install_root: /opt/IBM/WebSphere/AppServer
    profile_name: AppSrv01
    profile_type: application_server
    server_name: server1
    state: started
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
'''

RETURN = r'''
before:
  description: Runtime state before the operation.
  returned: always
  type: dict
after:
  description: Runtime state after the operation.
  returned: always
  type: dict
operation:
  description: Lifecycle operation requested.
  returned: always
  type: str
'''

import os
import time

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    common_wsadmin_argument_spec,
    profile_root,
    run_checked,
    temporary_in_place_ipc_credentials,
    temporary_in_place_soap_credentials,
)


def process_definition(module):
    profile_path = profile_root(module.params["install_root"], module.params["profile_name"])
    profile_type = module.params["profile_type"]
    if profile_type == "dmgr":
        process_name = "dmgr"
        start = [os.path.join(profile_path, "bin", "startManager.sh")]
        stop = [os.path.join(profile_path, "bin", "stopManager.sh")]
    elif profile_type == "node":
        process_name = "nodeagent"
        start = [os.path.join(profile_path, "bin", "startNode.sh")]
        stop = [os.path.join(profile_path, "bin", "stopNode.sh")]
    else:
        process_name = module.params["server_name"]
        start = [os.path.join(profile_path, "bin", "startServer.sh"), process_name]
        stop = [os.path.join(profile_path, "bin", "stopServer.sh"), process_name]
    status = [os.path.join(profile_path, "bin", "serverStatus.sh"), process_name]
    return profile_path, process_name, start, stop, status


def require_executables(module, commands):
    for command in commands:
        executable = command[0]
        if not os.access(executable, os.X_OK):
            module.fail_json(
                msg="WebSphere profile lifecycle script is missing or not executable",
                path=executable,
            )


def with_credentials(module, profile_path, argv, acceptable_rc=None):
    soap_properties = os.path.join(profile_path, "properties", "soap.client.props")
    ipc_properties = os.path.join(profile_path, "properties", "ipc.client.props")
    with temporary_in_place_soap_credentials(
        module,
        soap_properties,
        module.params["install_root"],
        module.params["profile_name"],
    ):
        with temporary_in_place_ipc_credentials(
            module,
            ipc_properties,
            module.params["install_root"],
            module.params["profile_name"],
        ):
            return run_checked(module, argv, acceptable_rc=acceptable_rc)


def runtime_status(module, profile_path, process_name, status_command):
    rc, stdout, stderr = with_credentials(
        module,
        profile_path,
        status_command,
        acceptable_rc=[0, 1, 2, 3],
    )
    output = "\n".join(value for value in (stdout, stderr) if value)
    normalized = output.lower()
    running_markers = ("admu0508i", " is started")
    stopped_markers = (
        "admu0509i",
        "appears to be stopped",
        "cannot be reached",
        "is stopped",
    )
    if any(marker in normalized for marker in running_markers):
        running = True
    elif any(marker in normalized for marker in stopped_markers):
        running = False
    else:
        module.fail_json(
            msg="Unable to determine WebSphere profile runtime state",
            process=process_name,
            rc=rc,
            stdout=stdout,
            stderr=stderr,
        )
    return {
        "profile": module.params["profile_name"],
        "profile_type": module.params["profile_type"],
        "process": process_name,
        "running": running,
        "status_lines": [line for line in output.splitlines() if line.strip()],
    }


def wait_for_state(module, profile_path, process_name, status_command, expected):
    deadline = time.time() + module.params["timeout"]
    last = None
    while time.time() <= deadline:
        last = runtime_status(module, profile_path, process_name, status_command)
        if last["running"] == expected:
            return last
        time.sleep(2)
    module.fail_json(
        msg="WebSphere profile did not reach the requested runtime state",
        process=process_name,
        expected_running=expected,
        last=last,
    )


def main():
    spec = common_wsadmin_argument_spec()
    spec.update({
        "profile_type": {
            "type": "str",
            "choices": ["dmgr", "node", "application_server"],
            "required": True,
        },
        "server_name": {"type": "str", "default": "server1"},
        "state": {
            "type": "str",
            "choices": ["started", "stopped", "restarted"],
            "default": "started",
        },
    })
    module = AnsibleModule(argument_spec=spec, supports_check_mode=True)
    profile_path, process_name, start, stop, status = process_definition(module)
    require_executables(module, [start, stop, status])

    before = runtime_status(module, profile_path, process_name, status)
    requested = module.params["state"]
    changed = (
        requested == "restarted"
        or (requested == "started" and not before["running"])
        or (requested == "stopped" and before["running"])
    )
    expected_running = requested != "stopped"

    if module.check_mode or not changed:
        after = dict(before)
        if module.check_mode and changed:
            after["running"] = expected_running
        module.exit_json(changed=changed, before=before, after=after, operation=requested)

    if requested in ("stopped", "restarted") and before["running"]:
        with_credentials(module, profile_path, stop)
        wait_for_state(module, profile_path, process_name, status, False)
    if requested in ("started", "restarted"):
        run_checked(module, start)

    after = wait_for_state(module, profile_path, process_name, status, expected_running)
    module.exit_json(changed=True, before=before, after=after, operation=requested)


if __name__ == "__main__":
    main()
