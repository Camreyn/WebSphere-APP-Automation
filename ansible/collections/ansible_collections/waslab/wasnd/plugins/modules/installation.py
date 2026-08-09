#!/usr/bin/python
# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later
from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r'''
---
module: installation
short_description: Manage IBM WebSphere ND installation lifecycle
version_added: "0.1.0"
description:
  - Installs or updates genuine WebSphere Network Deployment with IBM Installation Manager.
  - Licensed media must already be mounted on the managed host; this module never downloads IBM software.
options:
  state:
    description: Whether WebSphere ND is installed or guardedly uninstalled.
    choices: [present, absent]
    type: str
    default: present
  media_root:
    description: Read-only root containing the Installation Manager ZIP and repositories.
    type: path
    default: /was855
  version:
    description: Exact version expected from versionInfo.sh after installation.
    type: str
    default: 9.0.5.28
  install_root:
    description: WebSphere installation directory.
    type: path
    default: /opt/WebSphere/AppServers
  im_install_root:
    description: IBM Installation Manager installation directory.
    type: path
    default: /opt/IBM/InstallationManager
  shared_resources_root:
    description: IBM Installation Manager shared-resources directory.
    type: path
    default: /opt/IBM/IMShared
  was_package_id:
    description: IBM Installation Manager ND offering ID.
    type: str
    default: com.ibm.websphere.ND.v90
  java_package_id:
    description: IBM Java offering ID installed with ND.
    type: str
    default: com.ibm.java.jdk.v8
  log_dir:
    description: Persistent directory for Installation Manager logs.
    type: path
    default: /var/log/wasnd-ansible
  allow_destructive:
    description: Explicitly authorize package uninstallation.
    type: bool
    default: false
author:
  - WAS ND Lab Maintainers (@waslab)
'''

EXAMPLES = r'''
- name: Install exact WebSphere ND level from the legacy media mount
  become: true
  waslab.wasnd.installation:
    media_root: /was855
    version: 9.0.5.28
    state: present
'''

RETURN = r'''
before:
  description: Product state before the operation.
  returned: always
  type: dict
after:
  description: Product state after the operation.
  returned: always
  type: dict
repositories:
  description: Repository directories used by Installation Manager.
  returned: when state is present
  type: list
  elements: str
'''

import glob
import os
import re
import shutil
import tempfile

from ansible.module_utils.basic import AnsibleModule
from ansible_collections.waslab.wasnd.plugins.module_utils._common import (
    DEFAULT_IM_ROOT,
    DEFAULT_INSTALL_ROOT,
    DEFAULT_MEDIA_ROOT,
    DEFAULT_SHARED_ROOT,
    ensure_private_directory,
    require_destructive,
    run_checked,
)


def normalized_version(value):
    return tuple(int(item) for item in re.findall(r"\d+", value or ""))


def product_state(module):
    command = os.path.join(module.params["install_root"], "bin", "versionInfo.sh")
    if not os.access(command, os.X_OK):
        return {"installed": False, "edition": None, "version": None}
    unused_rc, stdout, unused_stderr = run_checked(module, [command, "-ifixes"])
    match = re.search(r"(?im)^\s*Version\s+([0-9][^\s]*)", stdout)
    edition = "Network Deployment" if re.search(r"Network Deployment|\bND\b", stdout, re.I) else "unknown"
    return {
        "installed": True,
        "edition": edition,
        "version": match.group(1) if match else None,
    }


def discover_repositories(media_root):
    configs = glob.glob(os.path.join(media_root, "**", "repository.config"), recursive=True)
    return sorted(set(os.path.dirname(path) for path in configs))


def ensure_installation_manager(module):
    imcl = os.path.join(module.params["im_install_root"], "eclipse", "tools", "imcl")
    if os.access(imcl, os.X_OK):
        return imcl, False
    installers = glob.glob(
        os.path.join(module.params["media_root"], "**", "agent.installer.linux.gtk.x86_64*.zip"),
        recursive=True,
    )
    if len(installers) != 1:
        module.fail_json(
            msg="Expected exactly one Linux x86-64 Installation Manager ZIP",
            media_root=module.params["media_root"],
            installers=installers,
        )
    if module.check_mode:
        return imcl, True
    extraction = tempfile.mkdtemp(prefix="waslab-im-", dir=module.tmpdir)
    try:
        run_checked(module, ["unzip", "-q", installers[0], "-d", extraction])
        candidates = glob.glob(os.path.join(extraction, "**", "installc"), recursive=True)
        if len(candidates) != 1:
            module.fail_json(msg="Installation Manager ZIP did not contain one installc", candidates=candidates)
        os.chmod(candidates[0], 0o755)
        log_path = os.path.join(module.params["log_dir"], "installation-manager-install.xml")
        run_checked(module, [
            candidates[0],
            "-acceptLicense",
            "-installationDirectory", module.params["im_install_root"],
            "-log", log_path,
        ])
    finally:
        shutil.rmtree(extraction, ignore_errors=True)
    if not os.access(imcl, os.X_OK):
        module.fail_json(msg="Installation Manager completed but imcl is unavailable", path=imcl)
    return imcl, True


def list_registered_profiles(module):
    command = os.path.join(module.params["install_root"], "bin", "manageprofiles.sh")
    if not os.access(command, os.X_OK):
        return []
    unused_rc, stdout, unused_stderr = run_checked(module, [command, "-listProfiles"])
    return re.findall(r"[A-Za-z0-9_.-]+", stdout.strip("[] \r\n"))


def main():
    module = AnsibleModule(argument_spec={
        "state": {"type": "str", "choices": ["present", "absent"], "default": "present"},
        "media_root": {"type": "path", "default": DEFAULT_MEDIA_ROOT},
        "version": {"type": "str", "default": "9.0.5.28"},
        "install_root": {"type": "path", "default": DEFAULT_INSTALL_ROOT},
        "im_install_root": {"type": "path", "default": DEFAULT_IM_ROOT},
        "shared_resources_root": {"type": "path", "default": DEFAULT_SHARED_ROOT},
        "was_package_id": {"type": "str", "default": "com.ibm.websphere.ND.v90"},
        "java_package_id": {"type": "str", "default": "com.ibm.java.jdk.v8"},
        "log_dir": {"type": "path", "default": "/var/log/wasnd-ansible"},
        "allow_destructive": {"type": "bool", "default": False},
    }, supports_check_mode=True)

    before = product_state(module)
    desired = module.params["state"]
    if desired == "absent":
        require_destructive(module)
        if not before["installed"]:
            module.exit_json(changed=False, before=before, after=before)
        profiles = list_registered_profiles(module)
        if profiles:
            module.fail_json(msg="Remove all registered profiles before uninstalling WebSphere", profiles=profiles)
        imcl = os.path.join(module.params["im_install_root"], "eclipse", "tools", "imcl")
        if not os.access(imcl, os.X_OK):
            module.fail_json(msg="Cannot uninstall WebSphere because imcl is unavailable", path=imcl)
        if not module.check_mode:
            ensure_private_directory(module.params["log_dir"])
            run_checked(module, [
                imcl, "uninstall", module.params["was_package_id"], module.params["java_package_id"],
                "-installationDirectory", module.params["install_root"],
                "-log", os.path.join(module.params["log_dir"], "was-uninstall.xml"),
            ])
        module.exit_json(
            changed=True,
            before=before,
            after={"installed": False, "edition": None, "version": None},
        )

    if before["installed"] and before["edition"] != "Network Deployment":
        module.fail_json(msg="Existing product is not WebSphere Network Deployment", detected=before)
    if before["installed"] and before["version"] == module.params["version"]:
        module.exit_json(changed=False, before=before, after=before, repositories=[])
    if (before["installed"] and before["version"] and
            normalized_version(before["version"]) > normalized_version(module.params["version"])):
        module.fail_json(
            msg="Implicit WebSphere downgrade is not supported",
            installed_version=before["version"],
            requested_version=module.params["version"],
        )
    if not os.path.isdir(module.params["media_root"]):
        module.fail_json(msg="Licensed IBM media root is not mounted", media_root=module.params["media_root"])
    repositories = discover_repositories(module.params["media_root"])
    if not repositories:
        module.fail_json(msg="No repository.config files were found", media_root=module.params["media_root"])

    if not module.check_mode:
        ensure_private_directory(module.params["log_dir"])
        for path in (
            module.params["im_install_root"],
            module.params["shared_resources_root"],
            module.params["install_root"],
        ):
            if not os.path.isdir(path):
                os.makedirs(path)
    imcl, im_changed = ensure_installation_manager(module)
    repository_csv = ",".join(repositories)
    if not module.check_mode:
        unused_rc, available, unused_stderr = run_checked(
            module,
            [imcl, "listAvailablePackages", "-repositories", repository_csv, "-long"],
        )
        for package in (module.params["was_package_id"], module.params["java_package_id"]):
            if package not in available:
                module.fail_json(msg="Required IBM offering is absent from the repository set", package=package)
        run_checked(module, [
            imcl, "install", module.params["was_package_id"], module.params["java_package_id"],
            "-repositories", repository_csv,
            "-installationDirectory", module.params["install_root"],
            "-sharedResourcesDirectory", module.params["shared_resources_root"],
            "-acceptLicense", "-showProgress",
            "-log", os.path.join(module.params["log_dir"], "was-nd-install.xml"),
        ])
        after = product_state(module)
        if after["edition"] != "Network Deployment" or after["version"] != module.params["version"]:
            module.fail_json(
                msg="Installed product does not match the requested ND level",
                requested_version=module.params["version"],
                detected=after,
            )
    else:
        after = {
            "installed": True,
            "edition": "Network Deployment",
            "version": module.params["version"],
        }
    module.exit_json(
        changed=True,
        before=before,
        after=after,
        installation_manager_changed=im_changed,
        repositories=repositories,
    )


if __name__ == "__main__":
    main()
