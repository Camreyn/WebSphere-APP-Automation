from __future__ import annotations

import copy
import importlib.util
import pathlib

import yaml


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTROLLER_UTIL = (
    ROOT
    / "ansible"
    / "collections"
    / "ansible_collections"
    / "waslab"
    / "wasnd"
    / "plugins"
    / "module_utils"
    / "_controller.py"
)


def load_controller_utility():
    spec = importlib.util.spec_from_file_location("_controller", CONTROLLER_UTIL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def credential(identifier: int, name: str, type_name: str) -> dict:
    return {
        "id": identifier,
        "name": name,
        "summary_fields": {"credential_type": {"name": type_name}},
    }


class FakeControllerApi:
    api_prefix = "/api/v2"

    def __init__(self, desired_survey: dict) -> None:
        self.setup_credentials = [
            credential(1, "AAP self API", "Red Hat Ansible Automation Platform"),
            credential(2, "Production SSH", "Machine"),
            credential(3, "Production wsadmin", "WebSphere Administrative Credential"),
        ]
        self.target_credentials = [
            self.setup_credentials[0],
            self.setup_credentials[1],
            credential(4, "Stale vault", "Vault"),
        ]
        self.target = {
            "id": 22,
            "url": "/api/v2/job_templates/22/",
            "name": "WAS - Reboot Nodes by Wave",
            "organization": 14,
            "description": "old description",
        }
        self.survey = {"name": "", "description": "", "spec": []}
        self.desired_survey = desired_survey
        self.calls: list[tuple[str, str, dict | None]] = []

    def endpoint(self, resource: str) -> str:
        return f"/api/v2/{resource.strip('/')}/"

    def collection(self, resource: str, params: dict | None = None) -> list[dict]:
        if resource == "job_templates/7/credentials":
            return copy.deepcopy(self.setup_credentials)
        if resource == "job_templates/22/credentials":
            return copy.deepcopy(self.target_credentials)
        if resource == "job_templates":
            return [copy.deepcopy(self.target)]
        raise AssertionError(f"Unexpected collection: {resource} {params}")

    def request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
        params: dict | None = None,
    ) -> dict:
        self.calls.append((method, path, copy.deepcopy(payload)))
        if method == "PATCH" and path == self.target["url"]:
            self.target.update(payload or {})
            return copy.deepcopy(self.target)
        if path == "/api/v2/job_templates/22/credentials/" and method == "POST":
            assert payload
            if payload.get("disassociate"):
                self.target_credentials = [
                    item for item in self.target_credentials if item["id"] != payload["id"]
                ]
            else:
                item = next(
                    item for item in self.setup_credentials if item["id"] == payload["id"]
                )
                self.target_credentials.append(item)
            return {}
        if path == "/api/v2/job_templates/22/survey_spec/" and method == "GET":
            return copy.deepcopy(self.survey)
        if path == "/api/v2/job_templates/22/survey_spec/" and method == "POST":
            self.survey = copy.deepcopy(payload or {})
            return copy.deepcopy(self.survey)
        raise AssertionError(f"Unexpected request: {method} {path} {params} {payload}")


def test_controller_setup_updates_once_then_is_idempotent() -> None:
    controller = load_controller_utility()
    survey = {
        "name": "Wave reboot",
        "description": "Authorize a maintenance wave.",
        "spec": [
            {
                "question_name": "Authorize reboot",
                "question_description": "Must be explicitly enabled.",
                "required": True,
                "type": "multiplechoice",
                "variable": "was_maintenance_allow_reboot",
                "choices": "false\ntrue\n",
                "default": "false",
                "min": None,
                "max": None,
                "new_question": True,
            }
        ],
    }
    definition = {
        "version": 1,
        "credential_mode": "prompt",
        "templates": [
            {
                "name": "WAS - Reboot Nodes by Wave",
                "description": "current description",
                "playbook": "ansible/playbooks/was_wave_reboot.yml",
                "job_type": "run",
                "verbosity": 1,
                "allow_simultaneous": False,
                "ask_variables_on_launch": False,
                "ask_credential_on_launch": True,
                "ask_forks_on_launch": True,
                "forks": 0,
                "survey": survey,
            }
        ],
    }
    setup_template = {
        "id": 7,
        "project": 11,
        "inventory": 12,
        "execution_environment": 13,
        "organization": 14,
    }
    api = FakeControllerApi(survey)

    first = controller.configure_controller_templates(api, setup_template, definition)
    assert first["changed"] is True
    assert first["templates"][0]["action"] == "updated"
    assert first["templates"][0]["credentials_added"] == []
    assert first["templates"][0]["credentials_removed"] == [
        "AAP self API",
        "Production SSH",
        "Stale vault",
    ]
    assert first["templates"][0]["survey_changed"] is True
    assert first["credential_mode"] == "prompt"
    assert first["copied_credentials"] == []
    assert first["excluded_credentials"] == [
        "AAP self API",
        "Production SSH",
        "Production wsadmin",
    ]

    second = controller.configure_controller_templates(api, setup_template, definition)
    assert second["changed"] is False
    assert second["templates"][0]["action"] == "unchanged"
    assert second["templates"][0]["credentials_added"] == []
    assert second["templates"][0]["credentials_removed"] == []
    assert second["templates"][0]["survey_changed"] is False


def test_controller_setup_check_mode_makes_no_api_writes() -> None:
    controller = load_controller_utility()
    definition = yaml.safe_load(
        (ROOT / "config" / "aap" / "controller_setup.yml").read_text(
            encoding="utf-8"
        )
    )
    api = FakeControllerApi(definition["templates"][0]["survey"])
    original_target = copy.deepcopy(api.target)
    original_credentials = copy.deepcopy(api.target_credentials)
    original_survey = copy.deepcopy(api.survey)

    result = controller.configure_controller_templates(
        api,
        {
            "id": 7,
            "name": "WAS - Setup Automation",
            "project": 11,
            "inventory": 12,
            "execution_environment": 13,
            "organization": 14,
        },
        definition,
        check_mode=True,
    )

    assert result["changed"] is True
    assert result["templates"][0]["action"] == "updated"
    assert api.target == original_target
    assert api.target_credentials == original_credentials
    assert api.survey == original_survey
    assert all(method == "GET" for method, _, _ in api.calls)
