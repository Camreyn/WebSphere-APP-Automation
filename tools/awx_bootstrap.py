from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any
from urllib.parse import urljoin

import requests
import yaml


class AwxApi:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def authenticate(self) -> None:
        login_url = urljoin(self.base_url, "api/login/")
        html_headers = {"Accept": "text/html,application/xhtml+xml"}
        response = self.session.get(login_url, headers=html_headers, timeout=30)
        response.raise_for_status()
        csrf_token = self.session.cookies.get("csrftoken")
        if not csrf_token:
            raise RuntimeError("AWX login page did not issue a CSRF cookie")
        response = self.session.post(
            login_url,
            data={
                "username": self.username,
                "password": self.password,
                "next": "/api/",
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "X-CSRFToken": csrf_token,
                "Referer": login_url,
            },
            timeout=30,
        )
        response.raise_for_status()
        if not any(name.endswith("sessionid") for name in self.session.cookies.keys()):
            raise RuntimeError("AWX rejected the administrator login")
        print("AWX_AUTH=session")

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            headers = dict(kwargs.pop("headers", {}))
            headers.update(
                {
                    "X-CSRFToken": self.session.cookies.get("csrftoken", ""),
                    "Referer": self.base_url,
                }
            )
            kwargs["headers"] = headers
        response = self.session.request(method, url, timeout=90, **kwargs)
        if not response.ok:
            body = response.text[:4000]
            raise RuntimeError(f"AWX {method} {path} failed ({response.status_code}): {body}")
        if not response.content:
            return {}
        return response.json()

    def wait_ready(self, timeout: int = 900) -> None:
        deadline = time.monotonic() + timeout
        last_error = ""
        while time.monotonic() < deadline:
            try:
                payload = self.request("GET", "/api/v2/ping/")
                if payload.get("version"):
                    print(f"AWX_VERSION={payload['version']}")
                    return
            except Exception as exc:  # service may still be migrating
                last_error = str(exc)
            time.sleep(5)
        raise TimeoutError(f"AWX did not become ready: {last_error}")

    def find_one(self, endpoint: str, name: str, **filters: Any) -> dict[str, Any] | None:
        params = {"name": name, **filters}
        payload = self.request("GET", endpoint, params=params)
        results = payload.get("results", [])
        if len(results) > 1:
            raise RuntimeError(f"More than one {endpoint} object matched {params}")
        return results[0] if results else None

    def ensure(
        self,
        endpoint: str,
        name: str,
        payload: dict[str, Any],
        *,
        filters: dict[str, Any] | None = None,
        patch_always: bool = False,
    ) -> dict[str, Any]:
        existing = self.find_one(endpoint, name, **(filters or {}))
        desired = {"name": name, **payload}
        if existing is None:
            created = self.request("POST", endpoint, json=desired)
            print(f"CREATED={endpoint}:{name}:{created['id']}")
            return created

        changed = patch_always
        for key, value in desired.items():
            if key == "name":
                continue
            if existing.get(key) != value:
                changed = True
                break
        if changed:
            existing = self.request("PATCH", existing["url"], json=payload)
            print(f"UPDATED={endpoint}:{name}:{existing['id']}")
        else:
            print(f"UNCHANGED={endpoint}:{name}:{existing['id']}")
        return existing

    def associate(self, endpoint: str, object_id: int) -> None:
        current = self.request("GET", endpoint, params={"id": object_id})
        if any(item["id"] == object_id for item in current.get("results", [])):
            return
        self.request("POST", endpoint, json={"id": object_id})

    def wait_job(self, path: str, timeout: int = 600) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.request("GET", path)
            status = job.get("status")
            if status in {"successful", "failed", "error", "canceled"}:
                if status != "successful":
                    raise RuntimeError(
                        f"AWX job {path} ended as {status}: {json.dumps(job)[:2000]}"
                    )
                return job
            time.sleep(3)
        raise TimeoutError(f"AWX job {path} did not finish")


def read_secret(path: pathlib.Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise RuntimeError(f"Secret file is empty: {path}")
    return value


def read_optional_yaml(path: pathlib.Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a YAML mapping in {path}")
    return value


def ensure_survey(api: AwxApi, resource_url: str, survey: dict[str, Any]) -> None:
    endpoint = resource_url.rstrip("/") + "/survey_spec/"
    existing = api.request("GET", endpoint)
    comparable = {
        "name": existing.get("name", ""),
        "description": existing.get("description", ""),
        "spec": existing.get("spec", []),
    }
    if comparable == survey:
        print(f"SURVEY_UNCHANGED={resource_url}")
        return
    api.request("POST", endpoint, json=survey)
    print(f"SURVEY_UPDATED={resource_url}")


def ensure_workflow_node(
    api: AwxApi,
    workflow: dict[str, Any],
    identifier: str,
    unified_job_template: int | None,
) -> dict[str, Any]:
    endpoint = f"/api/v2/workflow_job_templates/{workflow['id']}/workflow_nodes/"
    payload = api.request("GET", endpoint, params={"identifier": identifier})
    results = payload.get("results", [])
    if len(results) > 1:
        raise RuntimeError(f"Workflow node identifier is not unique: {identifier}")
    desired = {
        "workflow_job_template": workflow["id"],
        "identifier": identifier,
        "all_parents_must_converge": False,
    }
    # A workflow approval is represented by AWX as a unified job template that
    # is created *after* its node.  Preserve that generated template on later
    # bootstrap runs instead of patching it back to null.
    if unified_job_template is not None or not results:
        desired["unified_job_template"] = unified_job_template
    if not results:
        node = api.request("POST", endpoint, json=desired)
        print(f"WORKFLOW_NODE_CREATED={identifier}:{node['id']}")
        return node
    node = results[0]
    changed = any(node.get(key) != value for key, value in desired.items())
    if changed:
        node = api.request("PATCH", node["url"], json=desired)
        print(f"WORKFLOW_NODE_UPDATED={identifier}:{node['id']}")
    else:
        print(f"WORKFLOW_NODE_UNCHANGED={identifier}:{node['id']}")
    return node


def ensure_workflow_edge(
    api: AwxApi,
    parent: dict[str, Any],
    edge: str,
    child: dict[str, Any],
) -> None:
    endpoint = f"/api/v2/workflow_job_template_nodes/{parent['id']}/{edge}/"
    api.associate(endpoint, child["id"])
    print(f"WORKFLOW_EDGE={parent['id']}:{edge}:{child['id']}")


def bootstrap(api: AwxApi, root: pathlib.Path) -> None:
    api.wait_ready()
    api.authenticate()

    wave_reboot_config = read_optional_yaml(root / "config" / "aap" / "wave_reboot.yml")
    if wave_reboot_config is None:
        raise RuntimeError("config/aap/wave_reboot.yml is required")
    wave_template_config = wave_reboot_config.get("template")
    wave_survey = wave_reboot_config.get("survey")
    if not isinstance(wave_template_config, dict) or not isinstance(wave_survey, dict):
        raise RuntimeError("Wave-reboot config requires template and survey mappings")
    wave_template_name = str(wave_template_config["name"])
    wave_local_playbook = str(wave_template_config["local_lab_playbook"])

    organization = api.ensure(
        "/api/v2/organizations/",
        "WAS Lab",
        {"description": "Local traditional WebSphere 9 Base and ND training environment"},
    )

    inventory_variables = {
        "ansible_user": "ansible",
        "ansible_python_interpreter": "/usr/bin/python3",
        "was_install_root": "/opt/WebSphere/AppServers",
        "was_admin_user": "wsadmin",
        "was_cell_name": "LabCell01",
        "was_cluster_name": "AppCluster01",
        "was_server_name": "server1",
        "was_cluster_members": [
            {"node": "Node01", "server": "server1"},
            {"node": "Node02", "server": "server1"},
        ],
    }
    inventory = api.ensure(
        "/api/v2/inventories/",
        "WAS ND Lab",
        {
            "description": "IBM Base ILAN plus the entitled-media WebSphere ND hosts on the Docker subnet",
            "organization": organization["id"],
            "variables": yaml.safe_dump(inventory_variables, sort_keys=False),
        },
        filters={"organization": organization["id"]},
    )

    host_definitions = {
        "was-base": {
            "ansible_host": "172.29.0.40",
            "was_install_root": "/opt/IBM/WebSphere/AppServer",
            "was_profile_name": "AppSrv01",
            "was_soap_host": "localhost",
            "was_soap_port": 8880,
        },
        "was-dmgr": {"ansible_host": "172.29.0.20"},
        "was-node1": {
            "ansible_host": "172.29.0.21",
            "was_node_name": "Node01",
            "was_maintenance_wave": 2,
        },
        "was-node2": {
            "ansible_host": "172.29.0.22",
            "was_node_name": "Node02",
            "was_maintenance_wave": 1,
        },
    }
    hosts: dict[str, dict[str, Any]] = {}
    for name, variables in host_definitions.items():
        hosts[name] = api.ensure(
            "/api/v2/hosts/",
            name,
            {
                "inventory": inventory["id"],
                "enabled": True,
                "variables": yaml.safe_dump(variables, sort_keys=False),
            },
            filters={"inventory": inventory["id"]},
        )

    groups: dict[str, dict[str, Any]] = {}
    for name in ("was_hosts", "was_base", "was_dmgr", "was_nodes"):
        groups[name] = api.ensure(
            "/api/v2/groups/",
            name,
            {"inventory": inventory["id"], "variables": "---\n{}\n"},
            filters={"inventory": inventory["id"]},
        )
    api.associate(f"/api/v2/groups/{groups['was_dmgr']['id']}/hosts/", hosts["was-dmgr"]["id"])
    api.associate(f"/api/v2/groups/{groups['was_base']['id']}/hosts/", hosts["was-base"]["id"])
    api.associate(f"/api/v2/groups/{groups['was_nodes']['id']}/hosts/", hosts["was-node1"]["id"])
    api.associate(f"/api/v2/groups/{groups['was_nodes']['id']}/hosts/", hosts["was-node2"]["id"])
    api.associate(f"/api/v2/groups/{groups['was_hosts']['id']}/children/", groups["was_dmgr"]["id"])
    api.associate(f"/api/v2/groups/{groups['was_hosts']['id']}/children/", groups["was_nodes"]["id"])

    machine_type = api.find_one("/api/v2/credential_types/", "Machine")
    if not machine_type:
        raise RuntimeError("Built-in AWX Machine credential type is unavailable")
    machine_credential = api.ensure(
        "/api/v2/credentials/",
        "WAS Lab SSH",
        {
            "description": "Generated SSH key for the traditional WebSphere lab hosts",
            "organization": organization["id"],
            "credential_type": machine_type["id"],
            "inputs": {
                "username": "ansible",
                "ssh_key_data": read_secret(root / ".secrets" / "ansible_lab"),
            },
        },
        filters={"organization": organization["id"]},
        patch_always=True,
    )

    was_credential_type = api.ensure(
        "/api/v2/credential_types/",
        "WebSphere Administrative Credential",
        {
            "description": "Injects protected WebSphere wsadmin variables into jobs",
            "kind": "cloud",
            "inputs": {
                "fields": [
                    {"id": "username", "type": "string", "label": "Username"},
                    {"id": "password", "type": "string", "label": "Password", "secret": True},
                ],
                "required": ["username", "password"],
            },
            "injectors": {
                "extra_vars": {
                    "was_admin_user": "{{ username }}",
                    "was_admin_password": "{{ password }}",
                }
            },
        },
    )
    was_credential = api.ensure(
        "/api/v2/credentials/",
        "WAS Lab wsadmin",
        {
            "description": "Administrative identity for the local LabCell01 cell",
            "organization": organization["id"],
            "credential_type": was_credential_type["id"],
            "inputs": {
                "username": "wsadmin",
                "password": read_secret(root / ".secrets" / "was_admin_password"),
            },
        },
        filters={"organization": organization["id"]},
        patch_always=True,
    )

    smtp_credential_type = api.ensure(
        "/api/v2/credential_types/",
        "WebSphere SMTP Relay Credential",
        {
            "description": "Injects protected SMTP relay settings for detailed release reports",
            "kind": "cloud",
            "inputs": {
                "fields": [
                    {"id": "host", "type": "string", "label": "SMTP host"},
                    {"id": "port", "type": "string", "label": "SMTP port"},
                    {"id": "username", "type": "string", "label": "Username"},
                    {"id": "password", "type": "string", "label": "Password", "secret": True},
                    {"id": "from_address", "type": "string", "label": "From address"},
                    {"id": "starttls", "type": "boolean", "label": "Use STARTTLS"},
                    {"id": "ssl", "type": "boolean", "label": "Use implicit TLS"},
                ],
                "required": ["host", "port", "from_address"],
            },
            "injectors": {
                "extra_vars": {
                    "was_smtp_host": "{{ host }}",
                    "was_smtp_port": "{{ port }}",
                    "was_smtp_username": "{{ username }}",
                    "was_smtp_password": "{{ password }}",
                    "was_smtp_from_address": "{{ from_address }}",
                    "was_smtp_starttls": "{{ starttls }}",
                    "was_smtp_ssl": "{{ ssl }}",
                }
            },
        },
    )
    smtp_config = read_optional_yaml(root / ".secrets" / "smtp.yml")
    smtp_credential: dict[str, Any] | None = None
    if smtp_config:
        required_smtp = [key for key in ("host", "port", "from_address") if not smtp_config.get(key)]
        if required_smtp:
            raise RuntimeError(f".secrets/smtp.yml is missing: {', '.join(required_smtp)}")
        smtp_credential = api.ensure(
            "/api/v2/credentials/",
            str(smtp_config.get("name", "WAS Team SMTP")),
            {
                "description": "SMTP relay used by clustered application release workflows",
                "organization": organization["id"],
                "credential_type": smtp_credential_type["id"],
                "inputs": {
                    "host": str(smtp_config["host"]),
                    "port": str(smtp_config["port"]),
                    "username": str(smtp_config.get("username", "")),
                    "password": str(smtp_config.get("password", "")),
                    "from_address": str(smtp_config["from_address"]),
                    "starttls": bool(smtp_config.get("starttls", False)),
                    "ssl": bool(smtp_config.get("ssl", False)),
                },
            },
            filters={"organization": organization["id"]},
            patch_always=True,
        )
        print(f"SMTP_CREDENTIAL={smtp_credential['name']}")
    else:
        print("SMTP_CREDENTIAL=not_configured")

    execution_environment = api.ensure(
        "/api/v2/execution_environments/",
        "WAS Lab EE",
        {
            "description": "Pinned AWX 24.6.1 execution environment for this lab",
            "organization": organization["id"],
            "image": "wasnd-lab-ee:24.6.1",
            "pull": "missing",
        },
        filters={"organization": organization["id"]},
    )

    project = api.ensure(
        "/api/v2/projects/",
        "WAS Lab Automation",
        {
            "description": "Local read-only Git project generated from ansible/",
            "organization": organization["id"],
            "scm_type": "git",
            "scm_url": "git://172.29.0.10:9418/was-lab.git",
            "scm_branch": "main",
            "scm_clean": True,
            "scm_delete_on_update": True,
            "scm_update_on_launch": True,
            "scm_update_cache_timeout": 0,
        },
        filters={"organization": organization["id"]},
    )

    update = api.request("POST", f"/api/v2/projects/{project['id']}/update/", json={})
    update_url = update.get("url") or f"/api/v2/project_updates/{update['id']}/"
    api.wait_job(update_url)
    print("PROJECT_SYNC=successful")

    template_definitions = [
        (
            "WAS Base - Start Server and Discovered Applications",
            "playbooks/was_base_start_discovered_apps.yml",
            False,
        ),
        ("WAS Base - Status and wsadmin Probe", "playbooks/was_base_status.yml", False),
        ("WAS Base - Deploy Sample Application", "playbooks/was_base_deploy_sample.yml", False),
        ("WAS Base - Restart Sample Application", "playbooks/was_base_restart_sample.yml", False),
        ("WAS Base - Deploy Test EARs", "playbooks/was_base_deploy_test_ears.yml", False),
        ("WAS Base - Health Check", "playbooks/was_base_healthcheck.yml", False),
        ("WAS - Status", "playbooks/was_status.yml", False),
        ("WAS - Start Cluster", "playbooks/was_start_cluster.yml", False),
        ("WAS - Stop Cluster", "playbooks/was_stop_cluster.yml", False),
        ("WAS - Synchronize Nodes", "playbooks/was_sync_nodes.yml", False),
        ("WAS - Rolling Restart", "playbooks/was_rolling_restart.yml", False),
        (wave_template_name, wave_local_playbook, False),
        ("WAS - Deploy Sample Application", "playbooks/was_deploy_sample.yml", False),
        ("WAS - Set JVM Heap", "playbooks/was_set_jvm_heap.yml", True),
        ("WAS - Collect Logs", "playbooks/was_collect_logs.yml", False),
        ("WAS - Health Check", "playbooks/was_healthcheck.yml", False),
    ]
    templates: dict[str, dict[str, Any]] = {}
    for name, playbook, ask_variables in template_definitions:
        is_wave_reboot = name == wave_template_name
        template = api.ensure(
            "/api/v2/job_templates/",
            name,
            {
                "description": (
                    str(wave_template_config["description"])
                    if is_wave_reboot
                    else f"Managed by tools/awx_bootstrap.py: {playbook}"
                ),
                "job_type": "run",
                "inventory": inventory["id"],
                "project": project["id"],
                "playbook": playbook,
                "execution_environment": execution_environment["id"],
                "verbosity": 1,
                "ask_variables_on_launch": ask_variables,
                "survey_enabled": is_wave_reboot,
            },
            filters={"organization": organization["id"]},
        )
        templates[name] = template
        api.associate(
            f"/api/v2/job_templates/{template['id']}/credentials/",
            machine_credential["id"],
        )
        api.associate(
            f"/api/v2/job_templates/{template['id']}/credentials/",
            was_credential["id"],
        )

    ensure_survey(api, templates[wave_template_name]["url"], wave_survey)

    operator_template = api.ensure(
        "/api/v2/job_templates/",
        "WAS - Update Existing Application",
        {
            "description": (
                "Four-field, catalog-free existing-application update with live WAS discovery, "
                "automatic export/rollback, health verification, and deployment-time log output"
            ),
            "job_type": "run",
            "inventory": inventory["id"],
            "project": project["id"],
            "playbook": "playbooks/was_existing_app_deploy.yml",
            "execution_environment": execution_environment["id"],
            "verbosity": 2,
            "ask_variables_on_launch": False,
            "survey_enabled": True,
            "allow_simultaneous": False,
            "extra_vars": yaml.safe_dump(
                {
                    "deployment_target_group": "was_base",
                    "was_deployment_profile_type": "application_server",
                    "was_deployment_sync_nodes": [],
                },
                sort_keys=False,
            ),
        },
        filters={"organization": organization["id"]},
    )
    api.associate(
        f"/api/v2/job_templates/{operator_template['id']}/credentials/",
        machine_credential["id"],
    )
    api.associate(
        f"/api/v2/job_templates/{operator_template['id']}/credentials/",
        was_credential["id"],
    )
    operator_survey = {
        "name": "Update an existing WebSphere application",
        "description": (
            "WAS supplies the existing targets and bindings; release.yml supplies the "
            "checksum and health check. Operators enter only these four values."
        ),
        "spec": [
            {
                "question_name": "Application name",
                "question_description": (
                    "Exact installed WAS application name. The first stage validates it "
                    "against the live cell and refuses new installs."
                ),
                "required": True,
                "type": "text",
                "variable": "deployment_application",
                "default": "",
                "min": 1,
                "max": 128,
                "new_question": True,
            },
            {
                "question_name": "Release version",
                "question_description": (
                    "Immutable version directory on the approved release share."
                ),
                "required": True,
                "type": "text",
                "variable": "deployment_version",
                "default": "",
                "min": 1,
                "max": 64,
                "new_question": True,
            },
            {
                "question_name": "Change ticket",
                "question_description": "Request, change, or incident number recorded in the AWX report.",
                "required": True,
                "type": "text",
                "variable": "change_ticket",
                "default": "",
                "min": 1,
                "max": 128,
                "new_question": True,
            },
            {
                "question_name": "Preflight only",
                "question_description": (
                    "Choose true to validate the live app, artifact, checksum, and health "
                    "configuration without changing the application."
                ),
                "required": True,
                "type": "multiplechoice",
                "variable": "preflight_only",
                "choices": "false\ntrue",
                "default": "false",
                "min": None,
                "max": None,
                "new_question": True,
            },
        ],
    }
    ensure_survey(api, operator_template["url"], operator_survey)

    release_templates: dict[str, dict[str, Any]] = {}
    for name, playbook, needs_machine, needs_was in (
        ("WAS EAR Release - Validate", "playbooks/was_ear_validate.yml", True, True),
        ("WAS EAR Release - Deploy", "playbooks/was_ear_deploy.yml", True, True),
        (
            "WAS EAR Release - Approval Rejected",
            "playbooks/was_ear_approval_rejected.yml",
            False,
            False,
        ),
    ):
        template = api.ensure(
            "/api/v2/job_templates/",
            name,
            {
                "description": f"Workflow-managed clustered application release phase: {playbook}",
                "job_type": "run",
                "inventory": inventory["id"],
                "project": project["id"],
                "playbook": playbook,
                "execution_environment": execution_environment["id"],
                "verbosity": 2,
                "ask_variables_on_launch": True,
                # Read-only validation and rejection reporting may overlap.
                # Serialize the shared deployment template so two AdminApp
                # updates never save the same Dmgr cell concurrently.
                "allow_simultaneous": name != "WAS EAR Release - Deploy",
            },
            filters={"organization": organization["id"]},
        )
        if needs_machine:
            api.associate(
                f"/api/v2/job_templates/{template['id']}/credentials/",
                machine_credential["id"],
            )
        if needs_was:
            api.associate(
                f"/api/v2/job_templates/{template['id']}/credentials/",
                was_credential["id"],
            )
        if smtp_credential:
            api.associate(
                f"/api/v2/job_templates/{template['id']}/credentials/",
                smtp_credential["id"],
            )
        release_templates[name] = template

    catalog_path = root / "ansible" / "vars" / "was_application_catalog.yml"
    catalog_document = read_optional_yaml(catalog_path)
    if not catalog_document or not isinstance(catalog_document.get("was_application_catalog"), dict):
        raise RuntimeError(f"Application catalog is missing or invalid: {catalog_path}")
    application_choices = sorted(
        key for key, value in catalog_document["was_application_catalog"].items()
        if isinstance(value, dict) and value.get("enabled", False)
    )
    if not application_choices:
        raise RuntimeError("Application catalog contains no enabled applications")
    default_recipients = ""
    if smtp_config:
        configured_to = smtp_config.get("default_to", [])
        if isinstance(configured_to, str):
            default_recipients = configured_to
        elif isinstance(configured_to, list):
            default_recipients = ", ".join(str(item) for item in configured_to)

    workflow = api.ensure(
        "/api/v2/workflow_job_templates/",
        "WAS - Deploy Clustered EAR",
        {
            "description": (
                "Validate immutable share artifact, request approval, deploy through Dmgr, "
                "sync nodes, health-check, roll back, and email a verbose report"
            ),
            "organization": organization["id"],
            "inventory": inventory["id"],
            "survey_enabled": True,
            "allow_simultaneous": True,
            "ask_variables_on_launch": False,
        },
        filters={"organization": organization["id"]},
    )
    survey = {
        "name": "Clustered WebSphere EAR release request",
        "description": "Every value is revalidated against the immutable release manifest after approval.",
        "spec": [
            {
                "question_name": "Application",
                "question_description": "Source-controlled application catalog key.",
                "required": True,
                "type": "multiplechoice",
                "variable": "deployment_application",
                "choices": "\n".join(application_choices),
                "default": application_choices[0],
                "min": None,
                "max": None,
                "new_question": True,
            },
            {
                "question_name": "Immutable release version",
                "question_description": "Versioned directory below the application's approved share root.",
                "required": True,
                "type": "text",
                "variable": "deployment_version",
                "default": "",
                "min": 1,
                "max": 64,
                "new_question": True,
            },
            {
                "question_name": "Approved EAR/WAR SHA-256",
                "question_description": "Must match both release.yml and the actual archive.",
                "required": True,
                "type": "text",
                "variable": "deployment_sha256",
                "default": "",
                "min": 64,
                "max": 64,
                "new_question": True,
            },
            {
                "question_name": "Change or request number",
                "question_description": "Ticket used for audit, lock ownership, and email reporting.",
                "required": True,
                "type": "text",
                "variable": "change_ticket",
                "default": "",
                "min": 1,
                "max": 128,
                "new_question": True,
            },
            {
                "question_name": "Requested by",
                "question_description": "Developer or release owner requesting deployment.",
                "required": True,
                "type": "text",
                "variable": "requested_by",
                "default": "",
                "min": 1,
                "max": 256,
                "new_question": True,
            },
            {
                "question_name": "Team email recipients",
                "question_description": "Comma-separated recipients for validation and final verbose reports.",
                "required": False,
                "type": "text",
                "variable": "notification_email_to",
                "default": default_recipients,
                "min": 0,
                "max": 1024,
                "new_question": True,
            },
            {
                "question_name": "Deployment strategy",
                "question_description": "maintenance stops the app first; in_place updates while running.",
                "required": True,
                "type": "multiplechoice",
                "variable": "deployment_strategy",
                "choices": "maintenance\nin_place",
                "default": "maintenance",
                "min": None,
                "max": None,
                "new_question": True,
            },
            {
                "question_name": "Automatically roll back on failure",
                "question_description": "Redeploy the previously recorded immutable artifact when available.",
                "required": True,
                "type": "multiplechoice",
                "variable": "auto_rollback",
                "choices": "true\nfalse",
                "default": "true",
                "min": None,
                "max": None,
                "new_question": True,
            },
            {
                "question_name": "Force deployment even when checksum is current",
                "question_description": "Normally unchanged artifacts return NO_CHANGE.",
                "required": True,
                "type": "multiplechoice",
                "variable": "force_deploy",
                "choices": "false\ntrue",
                "default": "false",
                "min": None,
                "max": None,
                "new_question": True,
            },
            {
                "question_name": "Send status email",
                "question_description": "Requires an SMTP relay credential on the workflow phase templates.",
                "required": True,
                "type": "multiplechoice",
                "variable": "send_email",
                "choices": "true\nfalse",
                "default": "true",
                "min": None,
                "max": None,
                "new_question": True,
            },
            {
                "question_name": "Release notes",
                "question_description": "Optional operator notes included in AWX artifacts and email.",
                "required": False,
                "type": "textarea",
                "variable": "release_notes",
                "default": "",
                "min": 0,
                "max": 4096,
                "new_question": True,
            },
        ],
    }
    ensure_survey(api, workflow["url"], survey)

    validation_node = ensure_workflow_node(
        api,
        workflow,
        "validate-immutable-release",
        release_templates["WAS EAR Release - Validate"]["id"],
    )
    approval_node = ensure_workflow_node(api, workflow, "operations-approval", None)
    if not approval_node.get("unified_job_template"):
        approval_template = api.request(
            "POST",
            f"/api/v2/workflow_job_template_nodes/{approval_node['id']}/create_approval_template/",
            json={
                "name": "Approve clustered WebSphere application deployment",
                "description": "Review the validation job and immutable SHA-256 before approval.",
                "timeout": 86400,
            },
        )
        print(f"WORKFLOW_APPROVAL_CREATED={approval_template.get('id', 'unknown')}")
        approval_node = api.request("GET", approval_node["url"])
    deployment_node = ensure_workflow_node(
        api,
        workflow,
        "deploy-and-verify",
        release_templates["WAS EAR Release - Deploy"]["id"],
    )
    rejected_node = ensure_workflow_node(
        api,
        workflow,
        "report-approval-rejected",
        release_templates["WAS EAR Release - Approval Rejected"]["id"],
    )
    ensure_workflow_edge(api, validation_node, "success_nodes", approval_node)
    ensure_workflow_edge(api, approval_node, "success_nodes", deployment_node)
    ensure_workflow_edge(api, approval_node, "failure_nodes", rejected_node)

    print("AWX_BOOTSTRAP_COMPLETE=true")


def main() -> None:
    parser = argparse.ArgumentParser(description="Idempotently seed AWX for the WebSphere lab.")
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        password = read_secret(root / ".secrets" / "awx_admin_password")
        api = AwxApi(args.url, "admin", password)
        bootstrap(api, root)
    except Exception as exc:
        print(f"AWX_BOOTSTRAP_ERROR={exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
