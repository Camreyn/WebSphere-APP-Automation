# Copyright: (c) 2026, WAS ND Lab Maintainers
# GNU General Public License v3.0 or later (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)
from __future__ import absolute_import, division, print_function

__metaclass__ = type


class WavePlanError(Exception):
    pass


def require_single(items, label):
    if len(items) != 1:
        raise WavePlanError("%s: expected exactly one, discovered %s" % (label, len(items)))
    return items[0]


def member_is_started(member):
    state = str(member.get("state", "")).upper()
    return state in ("STARTED", "RUNNING")


def build_wave_plan(topologies, cells, require_two_node_cells=True):
    if not isinstance(topologies, dict) or not topologies:
        raise WavePlanError("No maintenance-host topology was supplied")
    if not isinstance(cells, dict):
        raise WavePlanError("Cell discovery must be a mapping")

    local_nodes = {}
    dmgr_by_cell = {}
    dmgr_profiles = {}
    hosts_by_cell = {}
    for host, topology in sorted(topologies.items()):
        managed = require_single(
            topology.get("managed_profiles", []),
            "%s managed-node profile" % host,
        )
        if not managed.get("cell") or not managed.get("node"):
            raise WavePlanError(
                "%s: unable to discover the managed profile cell and node" % host
            )
        if not managed.get("owner"):
            raise WavePlanError("%s: unable to discover the managed profile owner" % host)
        local_nodes[host] = managed
        hosts_by_cell.setdefault(managed["cell"], []).append(host)

        local_dmgrs = topology.get("dmgr_profiles", [])
        if len(local_dmgrs) > 1:
            raise WavePlanError("%s: more than one Dmgr profile was discovered" % host)
        if local_dmgrs:
            dmgr = local_dmgrs[0]
            cell = dmgr.get("cell")
            if not cell:
                raise WavePlanError("%s: unable to discover the Dmgr cell" % host)
            if cell in dmgr_by_cell:
                raise WavePlanError(
                    "%s: Dmgr profiles were found on both %s and %s"
                    % (cell, dmgr_by_cell[cell], host)
                )
            if not dmgr.get("owner"):
                raise WavePlanError("%s: unable to discover the Dmgr profile owner" % host)
            if not dmgr.get("soap_port"):
                raise WavePlanError("%s: unable to discover the Dmgr SOAP port" % host)
            dmgr_by_cell[cell] = host
            dmgr_profiles[cell] = dmgr

    missing_dmgrs = sorted(set(hosts_by_cell) - set(dmgr_by_cell))
    if missing_dmgrs:
        raise WavePlanError(
            "No co-located Dmgr was discovered for cells: %s"
            % ", ".join(missing_dmgrs)
        )

    planned_hosts = {}
    cell_summaries = []
    for cell_name, member_hosts in sorted(hosts_by_cell.items()):
        if require_two_node_cells and len(member_hosts) != 2:
            raise WavePlanError(
                "%s: expected one Node 1/Node 2 pair, discovered %s managed hosts"
                % (cell_name, len(member_hosts))
            )
        dmgr_host = dmgr_by_cell[cell_name]
        if dmgr_host not in member_hosts:
            raise WavePlanError(
                "%s: Dmgr host %s does not also contain a managed-node profile"
                % (cell_name, dmgr_host)
            )
        if dmgr_host not in cells:
            raise WavePlanError("%s: live Dmgr discovery result is missing" % dmgr_host)
        cell_data = cells[dmgr_host]
        facts = cell_data.get("facts", {})
        if facts.get("cell") != cell_name:
            raise WavePlanError(
                "%s: local profile cell differs from live Dmgr cell %r"
                % (dmgr_host, facts.get("cell"))
            )

        all_members = []
        for cluster in facts.get("clusters", []):
            for member in cluster.get("members", []):
                all_members.append(
                    {
                        "cluster": cluster.get("name", ""),
                        "node": member.get("node", ""),
                        "name": member.get("name", ""),
                        "state": member.get("state", ""),
                    }
                )

        managed_nodes = [local_nodes[host]["node"] for host in member_hosts]
        if len(set(managed_nodes)) != len(managed_nodes):
            raise WavePlanError(
                "%s: more than one inventory host resolves to the same managed node"
                % cell_name
            )
        unexpected_member_nodes = sorted(
            set(item["node"] for item in all_members) - set(managed_nodes)
        )
        if unexpected_member_nodes:
            raise WavePlanError(
                "%s: live cluster members exist on nodes missing from the "
                "maintenance pair: %s"
                % (cell_name, ", ".join(unexpected_member_nodes))
            )

        applications = cell_data.get("applications", [])
        for host in sorted(member_hosts):
            node_profile = local_nodes[host]
            local_members = [
                item for item in all_members if item["node"] == node_profile["node"]
            ]
            if not local_members:
                raise WavePlanError(
                    "%s: node %s has no discovered cluster members"
                    % (host, node_profile["node"])
                )
            unavailable = [item for item in local_members if not member_is_started(item)]
            if unavailable:
                labels = [
                    "%s/%s=%s" % (item["cluster"], item["name"], item["state"])
                    for item in unavailable
                ]
                raise WavePlanError(
                    "%s: cluster members are not started before maintenance: %s"
                    % (host, ", ".join(labels))
                )

            expected_apps = []
            member_names = set(item["name"] for item in local_members)
            for application in applications:
                if not application.get("installed") or not application.get("running"):
                    continue
                for instance in application.get("runtime_instances", []):
                    if (
                        instance.get("node") == node_profile["node"]
                        and instance.get("process") in member_names
                    ):
                        expected_apps.append(
                            {
                                "name": application.get("name"),
                                "node": node_profile["node"],
                                "server": instance.get("process"),
                            }
                        )
            deduplicated_apps = []
            seen_apps = set()
            for application in expected_apps:
                key = (application["name"], application["node"], application["server"])
                if key not in seen_apps:
                    seen_apps.add(key)
                    deduplicated_apps.append(application)

            dmgr_profile = dmgr_profiles[cell_name]
            planned_hosts[host] = {
                "wave": 2 if host == dmgr_host else 1,
                "cell": cell_name,
                "node": node_profile["node"],
                "node_install_root": node_profile["install_root"],
                "node_profile_name": node_profile["name"],
                "node_os_user": node_profile["owner"],
                "dmgr_host": dmgr_host,
                "dmgr_install_root": dmgr_profile["install_root"],
                "dmgr_profile_name": dmgr_profile["name"],
                "dmgr_os_user": dmgr_profile["owner"],
                "dmgr_soap_port": dmgr_profile["soap_port"],
                "hosts_dmgr": host == dmgr_host,
                "members": [
                    {"cluster": item["cluster"], "node": item["node"], "name": item["name"]}
                    for item in local_members
                ],
                "expected_applications": deduplicated_apps,
            }

        cell_summaries.append(
            {
                "cell": cell_name,
                "dmgr_host": dmgr_host,
                "node_1": dmgr_host,
                "node_2": next(
                    (host for host in member_hosts if host != dmgr_host),
                    "",
                ),
                "clusters": sorted(set(item["cluster"] for item in all_members)),
            }
        )

    wave_1 = sorted(host for host, item in planned_hosts.items() if item["wave"] == 1)
    wave_2 = sorted(host for host, item in planned_hosts.items() if item["wave"] == 2)
    if not wave_1 or not wave_2:
        raise WavePlanError("Both automatically discovered maintenance waves are required")
    return {
        "hosts": planned_hosts,
        "wave_1": wave_1,
        "wave_2": wave_2,
        "recommended_forks": max(len(wave_1), len(wave_2)),
        "cells": cell_summaries,
    }
