from __future__ import annotations

import copy
import importlib.util
import pathlib
import re

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
    assert "runtime = runtime_info()" in jython.BRIDGE
    assert 'result["wsadmin_runtime"] = runtime' in jython.BRIDGE


def test_jython_bridge_stays_in_the_was_855_language_subset() -> None:
    bridge = load_utility("_jython").BRIDGE
    for incompatible in (
        "from __future__ import print_function",
        "import json",
        "bool(",
        "sorted(",
        "with open",
        "except Exception as",
        "lambda",
    ):
        assert incompatible not in bridge
    assert "except Exception, exc:" in bridge
    assert "print RESULT_PREFIX + repr(value)" in bridge
    assert not re.search(r"\b(?:True|False)\b", bridge)
    assert not any(
        re.search(r"\S+\s+if\s+.+\s+else\s+", line)
        for line in bridge.splitlines()
    )
    assert bridge.index("runtime = runtime_info()") < bridge.index(
        "result = handlers[operation](payload)"
    )


def test_wsadmin_codec_round_trips_values_without_modern_jython_literals() -> None:
    codec = load_utility("_wsadmin_codec")
    payload = {
        "check_mode": True,
        "disabled": False,
        "names": ["orders", "caf\N{LATIN SMALL LETTER E WITH ACUTE}"],
        "path": "/opt/IBM/it's safe",
        "escaped": "C:\\IBM\\O'Brien\nnext",
        "value": None,
    }
    encoded = codec.jython21_literal(payload)

    assert "True" not in encoded
    assert "False" not in encoded
    assert "\N{LATIN SMALL LETTER E WITH ACUTE}" not in encoded
    decoded = codec.parse_wsadmin_result(encoded)
    assert decoded == {
        "check_mode": 1,
        "disabled": 0,
        "names": ["orders", "caf\N{LATIN SMALL LETTER E WITH ACUTE}"],
        "path": "/opt/IBM/it's safe",
        "escaped": "C:\\IBM\\O'Brien\nnext",
        "value": None,
    }
    assert codec.parse_wsadmin_result("{'changed': 0}")["changed"] is False
    assert codec.parse_wsadmin_result('{"changed": true}')["changed"] is True


def test_product_discovery_distinguishes_was9_and_baw_on_was855() -> None:
    product = load_utility("_product")
    was9 = """
Installed Product
Name                  IBM WebSphere Application Server Network Deployment
Version               9.0.5.28
ID                    ND
"""
    baw = """
Installed Product
Name                  IBM WebSphere Application Server Network Deployment
Version               8.5.5.23
ID                    ND
Installed Product
Name                  IBM Business Automation Workflow Enterprise
Version               24.0.1.0
ID                    BPMPC
"""
    bpm = """
Installed Product
Name                  IBM WebSphere Application Server Network Deployment
Version               8.5.5.18
ID                    ND
Installed Product
Name                  IBM Business Process Manager Advanced
Version               8.6.0.0
ID                    BPMPC
"""

    was9_facts = product.product_facts(was9)
    baw_facts = product.product_facts(baw)
    assert was9_facts["family"] == "was"
    assert was9_facts["version"] == "9.0.5.28"
    assert was9_facts["edition"] == "Network Deployment"
    assert baw_facts["family"] == "baw"
    assert baw_facts["version"] == "8.5.5.23"
    assert baw_facts["workflow_version"] == "24.0.1.0"
    assert len(baw_facts["products"]) == 2
    assert product.product_facts(bpm)["family"] == "bpm"
    assert product.product_facts("")["family"] == "unknown"


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
    assert "/opt/ibm/Workflow/*" in topology.DEFAULT_INSTALL_ROOTS


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
                "product": {
                    "edition": "Network Deployment",
                    "version": "8.5.5.23" if app_number == 1 else "9.0.5.28",
                    "family": "baw" if app_number == 1 else "was",
                    "family_name": (
                        "IBM Business Automation Workflow Enterprise"
                        if app_number == 1
                        else "IBM WebSphere Application Server Network Deployment"
                    ),
                    "workflow_version": "24.0.1.0" if app_number == 1 else "",
                },
                "clusters": [{
                    "name": cluster,
                    "members": [
                        {"node": node_1, "name": "server1", "state": "STARTED"},
                        {"node": node_2, "name": "server2", "state": "STARTED"},
                    ],
                }],
            },
            "wsadmin_runtime": {
                "implementation": "Jython",
                "generation": "2.1" if app_number == 1 else "2.7",
                "version": "2.1" if app_number == 1 else "2.7.3",
                "supported": 1,
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
    assert plan["cells"][0]["platform"]["family"] == "baw"
    assert plan["cells"][0]["platform"]["jython_generation"] == "2.1"
    assert plan["cells"][1]["platform"]["family"] == "was"
    assert plan["cells"][1]["platform"]["jython_generation"] == "2.7"


def test_wave_plan_fails_before_changes_for_incomplete_live_topology() -> None:
    wave_plan = load_utility("_wave_plan")
    topologies, cells = sample_discovered_wave_inputs()
    unsafe_cells = copy.deepcopy(cells)
    unsafe_cells["app1_node1"]["facts"]["clusters"][0]["members"].append(
        {"node": "UnlistedNode03", "name": "server3", "state": "STARTED"}
    )

    with pytest.raises(wave_plan.WavePlanError, match="missing from the maintenance pair"):
        wave_plan.build_wave_plan(topologies, unsafe_cells)


def test_wave_plan_rejects_an_unrecognized_wsadmin_runtime_before_changes() -> None:
    wave_plan = load_utility("_wave_plan")
    topologies, cells = sample_discovered_wave_inputs()
    cells["app1_node1"]["wsadmin_runtime"]["generation"] = "2.5"

    with pytest.raises(wave_plan.WavePlanError, match="unsupported Jython generation"):
        wave_plan.build_wave_plan(topologies, cells)
