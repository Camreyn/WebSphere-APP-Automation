from __future__ import annotations

import copy
import importlib.util
import pathlib

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[1]
UTILS = (
    ROOT
    / "ansible"
    / "collections"
    / "ansible_collections"
    / "waslab"
    / "wasnd"
    / "plugins"
    / "module_utils"
)


def load_utility(name: str):
    spec = importlib.util.spec_from_file_location(name, UTILS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_property_replacement_is_idempotent() -> None:
    common = load_utility("_common")
    original = "alpha=1\ncom.ibm.SOAP.securityEnabled=false\nomega=2\n"
    updated = common.replace_property(
        original, "com.ibm.SOAP.securityEnabled", "true"
    )
    assert updated.count("com.ibm.SOAP.securityEnabled=true") == 1
    assert common.replace_property(
        updated, "com.ibm.SOAP.securityEnabled", "true"
    ) == updated


def test_property_append_and_secret_redaction() -> None:
    common = load_utility("_common")
    assert common.replace_property("alpha=1", "beta", "2") == "alpha=1\nbeta=2\n"
    assert common.redact("first=s3cret second=s3cret", ["s3cret"]) == (
        "first=******** second=********"
    )


def test_collection_defaults_match_the_lab_layout() -> None:
    common = load_utility("_common")
    assert common.DEFAULT_INSTALL_ROOT == "/opt/WebSphere/AppServers"
    assert common.DEFAULT_MEDIA_ROOT == "/was855"
    assert common.profile_root(common.DEFAULT_INSTALL_ROOT, "Dmgr01").replace("\\", "/") == (
        "/opt/WebSphere/AppServers/profiles/Dmgr01"
    )


def test_jython_bridge_has_supported_operations_and_machine_result_prefix() -> None:
    jython = load_utility("_jython")
    for operation in (
        "info", "application_info", "application_export", "cluster", "cluster_member",
        "jvm_heap", "node_sync", "application"
    ):
        assert f'"{operation}": operation_{operation}' in jython.BRIDGE
    assert "ANSIBLE_WAS_RESULT=" in jython.BRIDGE
    assert "-defaultbinding.virtual.host" in jython.BRIDGE


def test_topology_discovery_reads_profiles_without_inventory_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    topology = load_utility("_topology")
    install_root = ROOT / "tests" / "fixtures" / "topology" / "AppServer"
    managed = install_root / "profiles" / "AppSrv01"
    dmgr = install_root / "profiles" / "Dmgr01"

    monkeypatch.setattr(topology, "path_owner", lambda unused_path: "wasprod")
    managed_result = topology.inspect_profile(
        str(install_root), "AppSrv01", str(managed)
    )
    dmgr_result = topology.inspect_profile(str(install_root), "Dmgr01", str(dmgr))

    assert managed_result["type"] == "managed"
    assert managed_result["cell"] == "OrdersCell"
    assert managed_result["node"] == "OrdersNode02"
    assert managed_result["servers"] == ["server2"]
    assert managed_result["owner"] == "wasprod"
    assert dmgr_result["type"] == "dmgr"
    assert dmgr_result["cell"] == "OrdersCell"
    assert dmgr_result["soap_port"] == 8891
    assert topology.parse_profile_names("[Dmgr01, AppSrv01]\n") == [
        "Dmgr01", "AppSrv01"
    ]


def sample_discovered_wave_inputs() -> tuple[dict, dict]:
    topologies: dict = {}
    cells: dict = {}
    for app_number in (1, 2):
        cell = f"App{app_number}Cell"
        cluster = f"App{app_number}Cluster"
        node_1_host = f"app{app_number}_node1"
        node_2_host = f"app{app_number}_node2"
        node_1 = f"App{app_number}Node01"
        node_2 = f"App{app_number}Node02"
        root = f"/opt/app{app_number}/WebSphere/AppServer"
        topologies[node_1_host] = {
            "managed_profiles": [{
                "name": "AppSrv01", "install_root": root, "owner": "was",
                "cell": cell, "node": node_1,
            }],
            "dmgr_profiles": [{
                "name": "Dmgr01", "install_root": root, "owner": "was",
                "cell": cell, "node": f"App{app_number}DmgrNode",
                "soap_port": 8879 + app_number,
            }],
        }
        topologies[node_2_host] = {
            "managed_profiles": [{
                "name": "AppSrv01", "install_root": root, "owner": "was",
                "cell": cell, "node": node_2,
            }],
            "dmgr_profiles": [],
        }
        cells[node_1_host] = {
            "facts": {
                "cell": cell,
                "clusters": [{
                    "name": cluster,
                    "members": [
                        {"node": node_1, "name": "server1", "state": "STARTED"},
                        {"node": node_2, "name": "server2", "state": "STARTED"},
                    ],
                }],
            },
            "applications": [{
                "name": f"orders{app_number}",
                "installed": True,
                "running": True,
                "runtime_instances": [
                    {"node": node_1, "process": "server1"},
                    {"node": node_2, "process": "server2"},
                ],
            }],
        }
    return topologies, cells


def test_wave_plan_derives_pairs_members_apps_and_parallelism() -> None:
    wave_plan = load_utility("_wave_plan")
    topologies, cells = sample_discovered_wave_inputs()

    plan = wave_plan.build_wave_plan(topologies, cells)

    assert wave_plan.member_is_started({"state": "NOT_STARTED"}) is False
    assert plan["wave_1"] == ["app1_node2", "app2_node2"]
    assert plan["wave_2"] == ["app1_node1", "app2_node1"]
    assert plan["recommended_forks"] == 2
    assert plan["hosts"]["app1_node1"]["hosts_dmgr"] is True
    assert plan["hosts"]["app1_node2"]["hosts_dmgr"] is False
    assert plan["hosts"]["app1_node2"]["members"] == [{
        "cluster": "App1Cluster", "node": "App1Node02", "name": "server2"
    }]
    assert plan["hosts"]["app1_node2"]["expected_applications"] == [{
        "name": "orders1", "node": "App1Node02", "server": "server2"
    }]


def test_wave_plan_fails_before_changes_for_incomplete_live_topology() -> None:
    wave_plan = load_utility("_wave_plan")
    topologies, cells = sample_discovered_wave_inputs()
    unsafe_cells = copy.deepcopy(cells)
    unsafe_cells["app1_node1"]["facts"]["clusters"][0]["members"].append(
        {"node": "UnlistedNode03", "name": "server3", "state": "STARTED"}
    )

    with pytest.raises(wave_plan.WavePlanError, match="missing from the maintenance pair"):
        wave_plan.build_wave_plan(topologies, unsafe_cells)
