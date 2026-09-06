from __future__ import annotations

import io
import pathlib
import re
import zipfile

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_all_yaml_files_parse() -> None:
    paths = list(ROOT.rglob("*.yml")) + list(ROOT.rglob("*.yaml"))
    assert paths
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            list(yaml.safe_load_all(stream))


def test_compose_exposes_expected_topology() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {
        "portal", "scm", "lan-gateway", "was-base", "was-dmgr", "was-node1", "was-node2", "haproxy"
    }
    assert compose["services"]["portal"]["ports"] == [
        "${LAB_PORTAL_BIND_ADDRESS:-127.0.0.1}:${LAB_PORTAL_PORT:-8888}:80"
    ]
    assert compose["services"]["was-dmgr"]["volumes"] == [
        "was_dmgr_profile:/opt/WebSphere/AppServers/profiles/Dmgr01",
        "./artifacts/releases:/mnt/was-releases:ro",
    ]
    expected_node_volumes = {
        "was-node1": ["was_node1_profile:/opt/WebSphere/AppServers/profiles/AppSrv01"],
        "was-node2": ["was_node2_profile:/opt/WebSphere/AppServers/profiles/AppSrv01"],
    }
    for node, volumes in expected_node_volumes.items():
        assert compose["services"][node]["volumes"] == volumes
    assert compose["services"]["was-base"]["volumes"] == [
        "was_base_profile:/opt/IBM/WebSphere/AppServer/profiles/AppSrv01",
        "./artifacts/releases:/mnt/was-releases:ro",
    ]
    gateway = compose["services"]["lan-gateway"]
    assert gateway["profiles"] == ["lan"]
    assert gateway["networks"]["lab"]["ipv4_address"] == "172.29.0.50"
    assert {
        int(binding.rsplit(":", 2)[1]) for binding in gateway["ports"]
    } == {
        2220, 2221, 2222, 2230, 8080, 8404, 8879, 8880, 8888, 9043,
        9060, 9081, 9082, 9143, 9160, 9180, 9418, 9444, 9445, 9543, 32000,
    }


def test_official_base_image_wraps_ibm_ilan_without_emulation() -> None:
    dockerfile = (ROOT / "docker" / "was-base" / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "docker" / "was-base" / "entrypoint.sh").read_text(encoding="utf-8")
    combined = (dockerfile + entrypoint).lower()
    assert "icr.io/appcafe/websphere-traditional:9.0.5.28" in dockerfile
    assert "/work/start_server.sh" in entrypoint
    assert "runuser -u was" in entrypoint
    assert "liberty" not in combined


def test_was_image_is_nd_and_not_liberty() -> None:
    dockerfile = (ROOT / "docker" / "wasnd" / "Dockerfile").read_text(encoding="utf-8")
    installer = (ROOT / "docker" / "wasnd" / "install-was.sh").read_text(encoding="utf-8")
    combined = (dockerfile + installer).lower()
    assert "com.ibm.websphere.nd.v90" in combined
    assert "network deployment" in combined
    assert "versioninfo.sh" in combined
    assert "websphere-liberty" not in combined


def test_secure_runner_invokes_genuine_wsadmin_and_cleans_up() -> None:
    runner = (ROOT / "docker" / "wasnd" / "runtime" / "wsadmin-secure.sh").read_text(
        encoding="utf-8"
    )
    assert '${profile_root}/bin/wsadmin.sh' in runner
    assert "-Dcom.ibm.SOAP.ConfigURL" in runner
    assert "trap cleanup EXIT" in runner
    assert '\n  -password ' not in runner


def test_sample_war_contains_required_entries() -> None:
    war = ROOT / "ansible" / "files" / "was-lab.war"
    assert war.is_file(), "run .\\lab.ps1 init to generate the sample WAR"
    with zipfile.ZipFile(war) as archive:
        listener = "WEB-INF/classes/com/waslab/StartupDelayListener.class"
        assert {"index.jsp", "WEB-INF/web.xml", listener}.issubset(archive.namelist())
        assert not any(name.startswith("WEB-INF/classes/javax/servlet/") for name in archive.namelist())
        class_bytes = archive.read(listener)
        assert class_bytes[:4] == b"\xca\xfe\xba\xbe"
        assert int.from_bytes(class_bytes[6:8], "big") == 52
        descriptor = archive.read("WEB-INF/web.xml").decode("utf-8")
        assert "com.waslab.StartupDelayListener" in descriptor
        assert "<param-value>10</param-value>" in descriptor


def test_generated_test_ears_have_java_ee_web_modules() -> None:
    catalog = yaml.safe_load((ROOT / "config" / "test_ears.yml").read_text(encoding="utf-8"))
    assert len(catalog["test_ears"]) == 3
    for application in catalog["test_ears"]:
        key = application["key"]
        ear = ROOT / "ansible" / "files" / "test-ears" / f"{key}.ear"
        assert ear.is_file(), "run tools/build_test_ears.py to generate the test EARs"
        with zipfile.ZipFile(ear) as archive:
            assert {"META-INF/application.xml", f"{key}.war"}.issubset(archive.namelist())
            descriptor = archive.read("META-INF/application.xml").decode("utf-8")
            assert f"<web-uri>{key}.war</web-uri>" in descriptor
            assert f"<context-root>{application['context_root']}</context-root>" in descriptor
            with zipfile.ZipFile(io.BytesIO(archive.read(f"{key}.war"))) as web_archive:
                assert {"index.jsp", "WEB-INF/web.xml"}.issubset(web_archive.namelist())
                web_descriptor = web_archive.read("WEB-INF/web.xml").decode("utf-8")
                assert application["display_name"] in web_descriptor


def test_awx_templates_reference_real_playbooks() -> None:
    bootstrap = (ROOT / "tools" / "awx_bootstrap.py").read_text(encoding="utf-8")
    referenced = set(re.findall(r'"(playbooks/[^"\n]+\.yml)"', bootstrap))
    assert referenced
    for relative_path in referenced:
        assert (ROOT / "ansible" / relative_path).is_file()


def test_portal_contains_all_primary_service_ports() -> None:
    portal = (ROOT / "portal" / "index.html").read_text(encoding="utf-8")
    for port in (
        32000, 9418, 9043, 9060, 8879, 8080, 8404, 9081, 9444, 9082, 9445,
        2230, 8880, 9143, 9160, 9180, 9543,
    ):
        assert f'data-port="{port}"' in portal
    assert "data-current-host" in portal
    assert "WAS - Deploy Clustered EAR" in portal


def test_wasnd_collection_has_expected_public_surface() -> None:
    collection = ROOT / "ansible" / "collections" / "ansible_collections" / "waslab" / "wasnd"
    metadata = yaml.safe_load((collection / "galaxy.yml").read_text(encoding="utf-8"))
    assert metadata["namespace"] == "waslab"
    assert metadata["name"] == "wasnd"
    assert metadata["version"] == "0.1.0"
    modules = {path.stem for path in (collection / "plugins" / "modules").glob("*.py")}
    assert {
        "installation", "profile", "federation", "soap_credentials", "cluster",
        "profile_runtime", "cluster_member", "application", "jvm_heap", "node_sync", "cell_info", "wsadmin",
        "application_info", "application_export", "log_delta",
        "release_artifact", "release_lock", "release_record", "smtp_report",
        "aap_template_setup",
    }.issubset(modules)
    roles = {path.name for path in (collection / "roles").iterdir() if path.is_dir()}
    assert {
        "install", "deployment_manager", "managed_node", "cell", "rolling_restart",
        "wave_reboot", "collect_logs",
    }.issubset(roles)


def test_playbooks_use_the_collection_instead_of_legacy_role() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "ansible" / "playbooks").glob("*.yml")
    )
    assert "waslab.wasnd." in combined
    assert "name: was_wsadmin" not in combined


def test_lan_access_declares_the_approved_port_set() -> None:
    common = (ROOT / "scripts" / "LanAccess.Common.ps1").read_text(encoding="utf-8")
    declared = {int(value) for value in re.findall(r"\b\d{4,5}\b", common)}
    assert {
        2220, 2221, 2222, 2230, 8080, 8404, 8879, 8880, 8888, 9043, 9060,
        9081, 9082, 9143, 9160, 9180, 9418, 9444, 9445, 9543, 32000,
    }.issubset(declared)
    assert 49196 not in declared


def test_collection_usage_guide_covers_primary_workflows() -> None:
    guide = (
        ROOT
        / "ansible"
        / "collections"
        / "ansible_collections"
        / "waslab"
        / "wasnd"
        / "docs"
        / "usage.md"
    ).read_text(encoding="utf-8")
    for heading in (
        "## Install the collection",
        "## Inventory model",
        "## Supply credentials safely",
        "## Operate an existing cell",
        "## Provision a new cell",
        "## Role reference",
        "## Module reference",
        "## Destructive-operation safeguards",
        "## AWX usage",
        "## Troubleshooting",
    ):
        assert heading in guide
    for module in (
        "installation", "profile", "federation", "soap_credentials",
        "profile_runtime", "cell_info", "cluster", "cluster_member", "application", "jvm_heap",
        "application_info", "application_export", "log_delta", "node_sync", "wsadmin",
    ):
        assert f"`{module}`" in guide


def test_base_startup_uses_live_application_discovery() -> None:
    playbook = (
        ROOT / "ansible" / "playbooks" / "was_base_start_discovered_apps.yml"
    ).read_text(encoding="utf-8")
    assert "waslab.wasnd.profile_runtime" in playbook
    assert "waslab.wasnd.cell_info" in playbook
    assert "was_live_cell.facts.applications" in playbook
    assert "waslab.wasnd.application" in playbook
    assert "state: started" in playbook
    assert "was_application_catalog" not in playbook
    assert "Display the complete startup report in the AWX job log" in playbook


def test_wave_reboot_runs_node_pairs_in_parallel_with_a_hard_wave_gate() -> None:
    playbook = yaml.safe_load_all(
        (ROOT / "ansible" / "playbooks" / "was_wave_reboot.yml").read_text(
            encoding="utf-8"
        )
    )
    plays = list(playbook)[0]
    assert [play["hosts"] for play in plays] == [
        "localhost", "was_maintenance_wave_1", "was_maintenance_wave_2"
    ]
    assert plays[1]["strategy"] == "free"
    assert plays[2]["strategy"] == "free"
    assert "Node 2" in plays[1]["name"]
    assert "Node 1" in plays[2]["name"]
    gate = str(plays[2]["pre_tasks"])
    assert "was_maintenance_host_recovered" in gate
    preflight = str(plays[0]["tasks"])
    assert "was_maintenance_require_dmgr_on_wave_2" in preflight
    assert "was_maintenance_hosts_dmgr" in preflight

    role_tasks = yaml.safe_load(
        (
            ROOT / "ansible" / "collections" / "ansible_collections" / "waslab"
            / "wasnd" / "roles" / "wave_reboot" / "tasks" / "main.yml"
        ).read_text(encoding="utf-8")
    )
    combined = str(role_tasks)
    task_names = [task["name"] for task in role_tasks]
    assert "was_maintenance_allow_reboot" in combined
    assert "ansible.builtin.reboot" in combined
    assert "was_maintenance_health_urls" in combined
    assert task_names.index("Stop the co-located deployment manager last") < task_names.index(
        "Reboot the operating system and wait for its Ansible connection"
    )
    assert task_names.index(
        "Reboot the operating system and wait for its Ansible connection"
    ) < task_names.index("Start the co-located deployment manager first after reboot")
    assert task_names.index(
        "Start the co-located deployment manager first after reboot"
    ) < task_names.index("Wait for the recovered deployment-manager SOAP connector")
    assert task_names.index(
        "Wait for the recovered deployment-manager SOAP connector"
    ) < task_names.index("Start the node agent after reboot")

    inventory = yaml.safe_load(
        (ROOT / "ansible" / "inventory" / "lab.yml").read_text(encoding="utf-8")
    )
    hosts = inventory["all"]["children"]["was_nodes"]["hosts"]
    assert hosts["was-node2"]["was_maintenance_wave"] == 1
    assert hosts["was-node1"]["was_maintenance_wave"] == 2


def test_in_aap_setup_configures_templates_credentials_and_shared_surveys() -> None:
    config_path = ROOT / "config" / "aap" / "controller_setup.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    wave_templates = [
        template for template in config["templates"]
        if template["key"] == "wave_reboot"
    ]
    assert len(wave_templates) == 1
    wave_template = wave_templates[0]
    assert wave_template["name"] == "WAS - Reboot Nodes by Wave"
    assert (ROOT / wave_template["playbook"]).is_file()
    assert (ROOT / "ansible" / wave_template["local_lab_playbook"]).is_file()
    survey_variables = {
        question["variable"] for question in wave_template["survey"]["spec"]
    }
    assert {
        "was_maintenance_allow_reboot",
        "maintenance_inventory_group",
        "was_maintenance_require_health_checks",
        "was_maintenance_reboot_timeout",
        "was_maintenance_dmgr_start_timeout",
    }.issubset(survey_variables)
    authorization = next(
        question
        for question in wave_template["survey"]["spec"]
        if question["variable"] == "was_maintenance_allow_reboot"
    )
    assert authorization["type"] == "multiplechoice"
    assert authorization["default"] == "false"

    setup_playbook = (ROOT / "setup.yml").read_text(encoding="utf-8")
    for required_text in (
        "CONTROLLER_HOST",
        "CONTROLLER_OAUTH_TOKEN",
        "awx_job_template_id",
        "config/aap/controller_setup.yml",
        "waslab.wasnd.aap_template_setup",
    ):
        assert required_text in setup_playbook

    controller_module = (
        ROOT / "ansible" / "collections" / "ansible_collections" / "waslab"
        / "wasnd" / "plugins" / "module_utils" / "_controller.py"
    ).read_text(encoding="utf-8")
    for endpoint in ("job_templates", "survey_spec", "credentials"):
        assert endpoint in controller_module
    assert not (ROOT / ".github" / "workflows" / "configure-aap-wave-reboot.yml").exists()
    assert not (ROOT / "tools" / "configure_aap_wave_reboot.py").exists()
    assert not (ROOT / "requirements-aap-bootstrap.txt").exists()

    local_bootstrap = (ROOT / "tools" / "awx_bootstrap.py").read_text(encoding="utf-8")
    assert '"config" / "aap" / "controller_setup.yml"' in local_bootstrap
    assert "templates[wave_template_name]" in local_bootstrap
    assert "ensure_survey" in local_bootstrap

    root_ansible_config = (ROOT / "ansible.cfg").read_text(encoding="utf-8")
    assert "collections_path = ansible/collections" in root_ansible_config


def test_clustered_release_workflow_surface() -> None:
    catalog = yaml.safe_load(
        (ROOT / "ansible" / "vars" / "was_application_catalog.yml").read_text(
            encoding="utf-8"
        )
    )
    assert catalog["was_application_catalog"]["was-lab"]["cluster"] == "AppCluster01"
    for playbook in (
        "was_ear_validate.yml",
        "was_ear_deploy.yml",
        "was_ear_approval_rejected.yml",
    ):
        assert (ROOT / "ansible" / "playbooks" / playbook).is_file()
    bootstrap = (ROOT / "tools" / "awx_bootstrap.py").read_text(encoding="utf-8")
    assert "WAS - Deploy Clustered EAR" in bootstrap
    for variable in (
        "deployment_application",
        "deployment_version",
        "deployment_sha256",
        "change_ticket",
        "requested_by",
        "notification_email_to",
        "deployment_strategy",
        "auto_rollback",
        "force_deploy",
        "send_email",
    ):
        assert variable in bootstrap


def test_simple_existing_application_workflow_surface() -> None:
    playbook = (
        ROOT / "ansible" / "playbooks" / "was_existing_app_deploy.yml"
    ).read_text(encoding="utf-8")
    assert "was_application_catalog" not in playbook
    for module in (
        "profile_runtime", "application_info", "release_artifact", "release_lock",
        "application_export", "application", "release_record", "log_delta",
    ):
        assert f"waslab.wasnd.{module}" in playbook
    assert "AWX REPORT | Display the complete deployment report" in playbook
    assert "Publish the report as an AWX job artifact" in playbook
    bootstrap = (ROOT / "tools" / "awx_bootstrap.py").read_text(encoding="utf-8")
    assert "WAS - Update Existing Application" in bootstrap
    for variable in (
        "deployment_application", "deployment_version", "change_ticket", "preflight_only",
    ):
        assert variable in bootstrap


def test_existing_application_pipeline_is_operator_complete_and_linked() -> None:
    pipeline_path = (
        ROOT / "ansible" / "collections" / "ansible_collections" / "waslab"
        / "wasnd" / "docs" / "existing-application-pipeline.md"
    )
    pipeline = pipeline_path.read_text(encoding="utf-8")
    for heading in (
        "## Operator quick start",
        "## Pipeline overview",
        "## Release-producer pipeline",
        "## AWX execution stages",
        "## Success and recovery statuses",
        "## Logs and reports in AWX",
        "## Environment ownership",
        "## Production controls",
        "## Boundary: new applications",
    ):
        assert heading in pipeline
    for value in (
        "WAS - Update Existing Application",
        "deployment_application",
        "deployment_version",
        "change_ticket",
        "preflight_only",
        "release.yml",
        "was_deployment_report",
        "PREFLIGHT_OK",
        "SUCCESS",
        "NO_CHANGE",
        "FAILED_ROLLED_BACK",
        "FAILED_ROLLBACK_FAILED",
        "/api/v2/job_templates/${AWX_TEMPLATE_ID}/launch/",
    ):
        assert value in pipeline
    for stage in range(1, 9):
        assert f"{stage}/8" in pipeline

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    release_readme = (
        ROOT / "artifacts" / "releases" / "README.md"
    ).read_text(encoding="utf-8")
    usage = (
        ROOT / "ansible" / "collections" / "ansible_collections" / "waslab"
        / "wasnd" / "docs" / "usage.md"
    ).read_text(encoding="utf-8")
    assert (
        "ansible/collections/ansible_collections/waslab/wasnd/docs/"
        "existing-application-pipeline.md"
    ) in readme
    assert (
        "../../ansible/collections/ansible_collections/waslab/wasnd/docs/"
        "existing-application-pipeline.md"
    ) in release_readme
    assert "existing-application-pipeline.md" in usage
