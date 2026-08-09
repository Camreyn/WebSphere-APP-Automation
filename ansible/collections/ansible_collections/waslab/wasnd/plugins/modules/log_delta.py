#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: log_delta
short_description: Capture bounded traditional WebSphere log changes
version_added: "0.1.0"
description:
  - Marks current log offsets before a deployment or returns only content
    appended since a previous mark.
  - Detects truncation and rotation, caps output, and classifies common
    WebSphere warning and error message identifiers for readable AWX reports.
options:
  paths:
    description: Absolute SystemOut, SystemErr, or related log paths.
    type: list
    elements: path
    required: true
  mode:
    description: Record current offsets or read content since them.
    choices: [mark, delta]
    type: str
    default: mark
  offsets:
    description: Offset mapping returned by an earlier C(mode=mark) call.
    type: dict
    default: {}
  maximum_bytes:
    description: Maximum appended bytes retained per file.
    type: int
    default: 262144
  maximum_lines:
    description: Maximum appended lines retained per file.
    type: int
    default: 1000
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Mark application-server logs
  waslab.wasnd.log_delta:
    paths:
      - /opt/IBM/WebSphere/AppServer/profiles/AppSrv01/logs/server1/SystemOut.log
      - /opt/IBM/WebSphere/AppServer/profiles/AppSrv01/logs/server1/SystemErr.log
    mode: mark
  register: log_mark

- name: Read only deployment-time log lines
  waslab.wasnd.log_delta:
    paths: "{{ log_mark.offsets.keys() | list }}"
    mode: delta
    offsets: "{{ log_mark.offsets }}"
'''

RETURN = r'''
offsets:
  description: File identity and byte offset mapping.
  returned: always
  type: dict
files:
  description: Per-file appended lines and classified warning/error lines.
  returned: when mode is delta
  type: list
combined_lines:
  description: Appended lines prefixed by source filename.
  returned: when mode is delta
  type: list
'''

import os
import re

from ansible.module_utils.basic import AnsibleModule


ERROR_PATTERN = re.compile(r"(?:\b[A-Z]{4}\d{4}E:|\b(?:ERROR|EXCEPTION|FAILED|FAILURE)\b)", re.I)
WARNING_PATTERN = re.compile(r"(?:\b[A-Z]{4}\d{4}W:|\bWARN(?:ING)?\b)", re.I)


def file_mark(path):
    try:
        value = os.stat(path)
    except OSError as exc:
        return {"exists": False, "size": 0, "inode": None, "error": str(exc)}
    return {
        "exists": True,
        "size": int(value.st_size),
        "inode": int(value.st_ino),
        "modified_epoch": int(value.st_mtime),
    }


def read_delta(path, previous, maximum_bytes, maximum_lines):
    current = file_mark(path)
    if not current["exists"]:
        return {
            "path": path,
            "exists": False,
            "rotated": False,
            "truncated": False,
            "bytes_added": 0,
            "lines": [],
            "warnings": [],
            "errors": [],
            "error": current.get("error", "log file is unavailable"),
        }, current

    prior_exists = bool(previous.get("exists", False))
    rotated = (
        not prior_exists
        or previous.get("inode") != current.get("inode")
        or int(current["size"]) < int(previous.get("size", 0))
    )
    original_start = 0 if rotated else int(previous.get("size", 0))
    bytes_added = max(0, int(current["size"]) - original_start)
    start = original_start
    truncated = bytes_added > maximum_bytes
    if truncated:
        start = max(original_start, int(current["size"]) - maximum_bytes)
    with open(path, "rb") as stream:
        stream.seek(start)
        content = stream.read(maximum_bytes)
    lines = content.decode("utf-8", "replace").splitlines()
    if len(lines) > maximum_lines:
        lines = lines[-maximum_lines:]
        truncated = True
    errors = [line for line in lines if ERROR_PATTERN.search(line)]
    warnings = [line for line in lines if WARNING_PATTERN.search(line) and line not in errors]
    return {
        "path": path,
        "exists": True,
        "rotated": rotated,
        "truncated": truncated,
        "bytes_added": bytes_added,
        "lines": lines,
        "warnings": warnings,
        "errors": errors,
    }, current


def main():
    module = AnsibleModule(
        argument_spec={
            "paths": {"type": "list", "elements": "path", "required": True},
            "mode": {"type": "str", "choices": ["mark", "delta"], "default": "mark"},
            "offsets": {"type": "dict", "default": {}},
            "maximum_bytes": {"type": "int", "default": 262144},
            "maximum_lines": {"type": "int", "default": 1000},
        },
        supports_check_mode=True,
    )
    paths = module.params["paths"]
    if not paths:
        module.fail_json(msg="paths must contain at least one log file")
    if module.params["maximum_bytes"] < 1024:
        module.fail_json(msg="maximum_bytes must be at least 1024")
    if module.params["maximum_lines"] < 1:
        module.fail_json(msg="maximum_lines must be at least 1")

    if module.params["mode"] == "mark":
        offsets = {path: file_mark(path) for path in paths}
        module.exit_json(changed=False, offsets=offsets, files=[])

    offsets = module.params["offsets"]
    files = []
    current_offsets = {}
    combined = []
    for path in paths:
        result, current = read_delta(
            path,
            offsets.get(path, {}),
            module.params["maximum_bytes"],
            module.params["maximum_lines"],
        )
        files.append(result)
        current_offsets[path] = current
        label = os.path.basename(path)
        combined.extend(["[%s] %s" % (label, line) for line in result["lines"]])
    module.exit_json(
        changed=False,
        offsets=current_offsets,
        files=files,
        combined_lines=combined,
        warning_count=sum(len(item["warnings"]) for item in files),
        error_count=sum(len(item["errors"]) for item in files),
    )


if __name__ == "__main__":
    main()
