#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: topology_info
short_description: Discover local traditional WebSphere profiles and identities
version_added: "0.1.0"
description:
  - Finds registered or conventional WebSphere profiles on a managed host.
  - Identifies deployment-manager and managed-node profiles, their cell and
    node names, profile owner, local servers, and Dmgr SOAP connector port.
  - Uses profile scripts and configuration first, followed by guarded common
    name and app/dm directory-prefix fallbacks.
  - Performs read-only discovery and does not require per-host topology variables.
options:
  install_roots:
    description: Candidate WebSphere installation roots or glob expressions.
    type: list
    elements: path
    default:
      - /opt/WebSphere/AppServer
      - /opt/WebSphere/AppServers
      - /opt/IBM/WebSphere/AppServer
      - /opt/ibm/WebSphere/AppServer
      - /usr/IBM/WebSphere/AppServer
      - /opt/IBM/Workflow/*
      - /opt/ibm/Workflow/*
      - /opt/IBM/BPM/*
      - /opt/ibm/BPM/*
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Discover WebSphere profiles on every maintenance host
  become: true
  waslab.wasnd.topology_info:
  register: was_local_topology
'''

RETURN = r'''
profiles:
  description: All discovered profiles and their local topology.
  returned: always
  type: list
  elements: dict
dmgr_profiles:
  description: Discovered deployment-manager profiles.
  returned: always
  type: list
  elements: dict
managed_profiles:
  description: Discovered managed-node profiles.
  returned: always
  type: list
  elements: dict
'''

import os

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._topology import (
    DEFAULT_INSTALL_ROOTS,
    inspect_profile,
    parse_profile_names,
    unique_real_paths,
)


def registered_profile_paths(module, install_root):
    paths = {}
    profiles_root = os.path.join(install_root, "profiles")
    if os.path.isdir(profiles_root):
        for name in os.listdir(profiles_root):
            path = os.path.join(profiles_root, name)
            if os.path.isdir(path):
                paths[name] = path

    manageprofiles = os.path.join(install_root, "bin", "manageprofiles.sh")
    if not os.path.isfile(manageprofiles):
        return paths
    rc, stdout, unused_stderr = module.run_command(
        [manageprofiles, "-listProfiles"],
        check_rc=False,
    )
    if rc != 0:
        return paths
    for name in parse_profile_names(stdout):
        rc, path_output, unused_stderr = module.run_command(
            [manageprofiles, "-getPath", "-profileName", name],
            check_rc=False,
        )
        if rc != 0:
            continue
        candidates = [line.strip() for line in path_output.splitlines() if line.strip()]
        profile_path = next(
            (candidate for candidate in reversed(candidates) if os.path.isdir(candidate)),
            "",
        )
        if profile_path:
            paths[name] = profile_path
    return paths


def main():
    module = AnsibleModule(
        argument_spec={
            "install_roots": {
                "type": "list",
                "elements": "path",
                "default": list(DEFAULT_INSTALL_ROOTS),
            },
        },
        supports_check_mode=True,
    )
    requested = list(module.params["install_roots"])
    requested.extend(
        [
            "/opt/*/WebSphere/AppServer",
            "/opt/*/WebSphere/AppServers",
        ]
    )
    installations = []
    profiles = []
    seen_profiles = set()
    for install_root in unique_real_paths(requested):
        if not os.path.isdir(install_root):
            continue
        profile_paths = registered_profile_paths(module, install_root)
        if not profile_paths:
            continue
        installations.append(install_root)
        for name, path in sorted(profile_paths.items()):
            real_path = os.path.realpath(path)
            if real_path in seen_profiles:
                continue
            seen_profiles.add(real_path)
            profiles.append(inspect_profile(install_root, name, path))

    module.exit_json(
        changed=False,
        installations=installations,
        profiles=profiles,
        dmgr_profiles=[item for item in profiles if item["type"] == "dmgr"],
        managed_profiles=[item for item in profiles if item["type"] == "managed"],
    )


if __name__ == "__main__":
    main()
