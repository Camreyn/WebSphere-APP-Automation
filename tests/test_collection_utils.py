from __future__ import annotations

import importlib.util
import pathlib


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
