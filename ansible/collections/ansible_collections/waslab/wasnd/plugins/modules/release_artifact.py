#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: release_artifact
short_description: Validate an immutable WebSphere application archive
version_added: "0.1.0"
description:
  - Validates that a WAR or EAR is below an approved release root.
  - Verifies its SHA-256, size, ZIP integrity, and member paths without extracting it.
options:
  artifact_path:
    description: WAR or EAR path on the managed host.
    type: path
    required: true
  allowed_root:
    description: Canonical release root that must contain the artifact.
    type: path
    required: true
  expected_checksum:
    description: Required lowercase or uppercase SHA-256 value.
    type: str
    required: true
  expected_extension:
    description: Expected application archive type.
    choices: [ear, war]
    type: str
    required: true
  maximum_size_mb:
    description: Maximum accepted archive size in MiB.
    type: int
    default: 4096
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Validate an approved EAR
  waslab.wasnd.release_artifact:
    artifact_path: /mnt/releases/payroll/2026.08.08/payroll.ear
    allowed_root: /mnt/releases/payroll
    expected_checksum: "{{ requested_sha256 }}"
    expected_extension: ear
'''

RETURN = r'''
checksum:
  description: Calculated SHA-256.
  returned: always
  type: str
size:
  description: Archive size in bytes.
  returned: always
  type: int
entry_count:
  description: Number of ZIP entries.
  returned: always
  type: int
application_modules:
  description: Top-level WAR, JAR, and RAR entries found in the archive.
  returned: always
  type: list
  elements: str
'''

import hashlib
import os
import re
import zipfile

from ansible.module_utils.basic import AnsibleModule


SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def calculate_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_below(root, candidate):
    try:
        return os.path.commonpath([root, candidate]) == root and candidate != root
    except ValueError:
        return False


def unsafe_archive_entry(name):
    normalized = name.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return (
        normalized.startswith("/")
        or bool(re.match(r"^[A-Za-z]:", normalized))
        or ".." in parts
    )


def main():
    module = AnsibleModule(
        argument_spec={
            "artifact_path": {"type": "path", "required": True},
            "allowed_root": {"type": "path", "required": True},
            "expected_checksum": {"type": "str", "required": True},
            "expected_extension": {
                "type": "str",
                "choices": ["ear", "war"],
                "required": True,
            },
            "maximum_size_mb": {"type": "int", "default": 4096},
        },
        supports_check_mode=True,
    )
    artifact = os.path.realpath(module.params["artifact_path"])
    allowed_root = os.path.realpath(module.params["allowed_root"])
    expected_checksum = module.params["expected_checksum"].lower()
    extension = module.params["expected_extension"].lower()

    if not SHA256_PATTERN.match(expected_checksum):
        module.fail_json(msg="expected_checksum must contain exactly 64 hexadecimal characters")
    if not os.path.isdir(allowed_root):
        module.fail_json(msg="Approved release root does not exist", path=allowed_root)
    if not is_below(allowed_root, artifact):
        module.fail_json(
            msg="Artifact path escapes its approved release root",
            artifact_path=artifact,
            allowed_root=allowed_root,
        )
    if not os.path.isfile(artifact):
        module.fail_json(msg="Application archive does not exist", path=artifact)
    if not artifact.lower().endswith("." + extension):
        module.fail_json(
            msg="Application archive has the wrong extension",
            expected_extension=extension,
            path=artifact,
        )

    size = os.path.getsize(artifact)
    maximum_bytes = module.params["maximum_size_mb"] * 1024 * 1024
    if size > maximum_bytes:
        module.fail_json(
            msg="Application archive exceeds the configured size limit",
            size=size,
            maximum_bytes=maximum_bytes,
        )

    checksum = calculate_sha256(artifact)
    if checksum != expected_checksum:
        module.fail_json(
            msg="Application archive SHA-256 does not match the approved value",
            expected_checksum=expected_checksum,
            actual_checksum=checksum,
        )

    try:
        with zipfile.ZipFile(artifact, "r") as archive:
            entries = archive.namelist()
            unsafe = [name for name in entries if unsafe_archive_entry(name)]
            if unsafe:
                module.fail_json(
                    msg="Application archive contains unsafe member paths",
                    unsafe_entries=unsafe[:25],
                )
            corrupt = archive.testzip()
            if corrupt:
                module.fail_json(
                    msg="Application archive failed its ZIP integrity check",
                    corrupt_entry=corrupt,
                )
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        module.fail_json(msg="Application archive is not a readable ZIP file", error=str(exc))

    application_modules = sorted(
        name for name in entries
        if "/" not in name.strip("/") and name.lower().endswith((".war", ".jar", ".rar"))
    )
    module.exit_json(
        changed=False,
        artifact_path=artifact,
        checksum=checksum,
        size=size,
        archive_type=extension,
        entry_count=len(entries),
        application_modules=application_modules,
        has_application_xml="META-INF/application.xml" in entries,
    )


if __name__ == "__main__":
    main()
