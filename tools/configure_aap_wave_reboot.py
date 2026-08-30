from __future__ import annotations

import argparse
import os
import pathlib
import time
from typing import Any
from urllib.parse import urljoin

import requests
import yaml


TERMINAL_STATUSES = {"successful", "failed", "error", "canceled"}


def required(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise RuntimeError(f"{label} is required")
    return normalized


def csv_values(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def requests_verify(value: str | None) -> bool | str:
    normalized = (value or "true").strip()
    if normalized.lower() in {"true", "1", "yes", "on"}:
        return True
    if normalized.lower() in {"false", "0", "no", "off"}:
        return False
    return normalized


def repository_url(explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    repository = os.getenv("GITHUB_REPOSITORY", "").strip()
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    if repository:
        return f"{server}/{repository}.git"
    raise RuntimeError("AAP_PROJECT_SCM_URL or GITHUB_REPOSITORY is required")


class ControllerApi:
    def __init__(
        self,
        host: str,
        token: str,
        *,
        api_prefix: str = "/api/v2",
        verify: bool | str = True,
    ) -> None:
        self.host = host.rstrip("/") + "/"
        self.api_prefix = "/" + (api_prefix or "/api/v2").strip("/")
        self.verify = verify
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
        )

    def endpoint(self, resource: str) -> str:
        return f"{self.api_prefix}/{resource.strip('/')}/"

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = urljoin(self.host, path.lstrip("/"))
        response = self.session.request(
            method,
            url,
            timeout=90,
            verify=self.verify,
            **kwargs,
        )
        if not response.ok:
            raise RuntimeError(
                f"AAP {method} {path} failed ({response.status_code}): "
                f"{response.text[:4000]}"
            )
        if not response.content:
            return {}
        return response.json()

    def named_results(self, resource: str, name: str) -> list[dict[str, Any]]:
        payload = self.request(
            "GET",
            self.endpoint(resource),
            params={"name": name},
        )
        return [item for item in payload.get("results", []) if item.get("name") == name]

    def find_named(
        self,
        resource: str,
        name: str,
        *,
        organization: int | None = None,
        allow_global: bool = False,
    ) -> dict[str, Any]:
        results = self.named_results(resource, name)
        if organization is not None:
            scoped = [item for item in results if item.get("organization") == organization]
            if scoped:
                results = scoped
            elif allow_global:
                results = [item for item in results if item.get("organization") in (None, 0)]
            else:
                results = []
        if len(results) != 1:
            raise RuntimeError(
                f"Expected exactly one {resource} named {name!r}; found {len(results)}"
            )
        return results[0]

    def ensure_named(
        self,
        resource: str,
        name: str,
        payload: dict[str, Any],
        *,
        organization: int | None = None,
    ) -> dict[str, Any]:
        results = self.named_results(resource, name)
        if organization is not None:
            results = [item for item in results if item.get("organization") == organization]
        desired = {"name": name, **payload}
        if not results:
            created = self.request("POST", self.endpoint(resource), json=desired)
            print(f"CREATED={resource}:{name}:{created['id']}")
            return created
        if len(results) != 1:
            raise RuntimeError(f"More than one {resource} matched {name!r}")
        existing = results[0]
        changed = any(existing.get(key) != value for key, value in desired.items())
        if changed:
            existing = self.request("PATCH", existing["url"], json=payload)
            print(f"UPDATED={resource}:{name}:{existing['id']}")
        else:
            print(f"UNCHANGED={resource}:{name}:{existing['id']}")
        return existing

    def associate(self, path: str, object_id: int) -> None:
        current = self.request("GET", path, params={"id": object_id})
        if any(item.get("id") == object_id for item in current.get("results", [])):
            return
        self.request("POST", path, json={"id": object_id})

    def wait_job(self, path: str, timeout: int = 900) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.request("GET", path)
            status = job.get("status")
            if status in TERMINAL_STATUSES:
                if status != "successful":
                    raise RuntimeError(f"AAP job {path} ended as {status}")
                return job
            time.sleep(3)
        raise TimeoutError(f"AAP job {path} did not finish within {timeout} seconds")


def load_config(path: pathlib.Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a YAML mapping in {path}")
    for key in ("project", "template", "survey"):
        if not isinstance(value.get(key), dict):
            raise RuntimeError(f"Missing {key} mapping in {path}")
    return value


def write_github_output(values: dict[str, Any]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")


def configure(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config(args.config)
    organization_name = args.organization or "Default"
    project_name = args.project_name or str(config["project"]["name"])
    template_name = args.template_name or str(config["template"]["name"])
    scm_branch = args.scm_branch or str(config["project"].get("scm_branch", "main"))
    job_credentials = csv_values(args.job_credentials)
    if not job_credentials:
        raise RuntimeError("AAP_JOB_CREDENTIALS must name the Machine and WebSphere credentials")

    api = ControllerApi(
        required(args.host, "AAP_HOST"),
        required(args.token, "AAP_OAUTH_TOKEN"),
        api_prefix=args.api_prefix,
        verify=requests_verify(args.validate_certs),
    )
    organization = api.find_named("organizations", organization_name)
    organization_id = int(organization["id"])
    inventory = api.find_named(
        "inventories",
        required(args.inventory, "AAP_INVENTORY"),
        organization=organization_id,
    )

    project_payload = {
        "description": config["project"]["description"],
        "organization": organization_id,
        "scm_type": "git",
        "scm_url": repository_url(args.scm_url),
        "scm_branch": scm_branch,
        "scm_clean": bool(config["project"].get("scm_clean", True)),
        "scm_delete_on_update": bool(config["project"].get("scm_delete_on_update", True)),
        "scm_update_on_launch": bool(config["project"].get("scm_update_on_launch", True)),
        "scm_update_cache_timeout": int(
            config["project"].get("scm_update_cache_timeout", 0)
        ),
    }
    if args.scm_credential:
        scm_credential = api.find_named(
            "credentials",
            args.scm_credential,
            organization=organization_id,
        )
        project_payload["credential"] = scm_credential["id"]

    project = api.ensure_named(
        "projects",
        project_name,
        project_payload,
        organization=organization_id,
    )
    if not args.skip_project_sync:
        update = api.request(
            "POST",
            f"{api.endpoint('projects')}{project['id']}/update/",
            json={},
        )
        update_url = update.get("url") or (
            f"{api.endpoint('project_updates')}{update['id']}/"
        )
        api.wait_job(update_url)
        print("PROJECT_SYNC=successful")

    template_payload: dict[str, Any] = {
        "description": config["template"]["description"],
        "job_type": config["template"].get("job_type", "run"),
        "inventory": inventory["id"],
        "project": project["id"],
        "playbook": config["template"]["playbook"],
        "verbosity": int(config["template"].get("verbosity", 1)),
        "allow_simultaneous": bool(config["template"].get("allow_simultaneous", False)),
        "ask_variables_on_launch": False,
        "survey_enabled": True,
    }
    if args.execution_environment:
        execution_environment = api.find_named(
            "execution_environments",
            args.execution_environment,
            organization=organization_id,
            allow_global=True,
        )
        template_payload["execution_environment"] = execution_environment["id"]

    template = api.ensure_named(
        "job_templates",
        template_name,
        template_payload,
        organization=organization_id,
    )
    for credential_name in job_credentials:
        credential = api.find_named(
            "credentials",
            credential_name,
            organization=organization_id,
        )
        api.associate(
            f"{api.endpoint('job_templates')}{template['id']}/credentials/",
            credential["id"],
        )
        print(f"TEMPLATE_CREDENTIAL={credential_name}")

    survey_endpoint = template["url"].rstrip("/") + "/survey_spec/"
    existing_survey = api.request("GET", survey_endpoint)
    desired_survey = config["survey"]
    comparable = {
        "name": existing_survey.get("name", ""),
        "description": existing_survey.get("description", ""),
        "spec": existing_survey.get("spec", []),
    }
    if comparable != desired_survey:
        api.request("POST", survey_endpoint, json=desired_survey)
        print(f"SURVEY_UPDATED={template_name}")
    else:
        print(f"SURVEY_UNCHANGED={template_name}")

    result = {
        "project_id": project["id"],
        "project_name": project_name,
        "template_id": template["id"],
        "template_name": template_name,
    }
    write_github_output(result)
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Idempotently configure the wave-reboot AAP project, template, and survey"
    )
    result.add_argument(
        "--config",
        type=pathlib.Path,
        default=pathlib.Path("config/aap/wave_reboot.yml"),
    )
    result.add_argument("--host", default=os.getenv("AAP_HOST"))
    result.add_argument("--token", default=os.getenv("AAP_OAUTH_TOKEN"))
    result.add_argument("--api-prefix", default=os.getenv("AAP_API_PREFIX", "/api/v2"))
    result.add_argument("--validate-certs", default=os.getenv("AAP_VALIDATE_CERTS", "true"))
    result.add_argument("--organization", default=os.getenv("AAP_ORGANIZATION", "Default"))
    result.add_argument("--inventory", default=os.getenv("AAP_INVENTORY"))
    result.add_argument(
        "--execution-environment",
        default=os.getenv("AAP_EXECUTION_ENVIRONMENT", ""),
    )
    result.add_argument("--project-name", default=os.getenv("AAP_PROJECT_NAME", ""))
    result.add_argument("--template-name", default=os.getenv("AAP_TEMPLATE_NAME", ""))
    result.add_argument("--scm-url", default=os.getenv("AAP_PROJECT_SCM_URL", ""))
    result.add_argument("--scm-branch", default=os.getenv("AAP_PROJECT_SCM_BRANCH", ""))
    result.add_argument("--scm-credential", default=os.getenv("AAP_SCM_CREDENTIAL", ""))
    result.add_argument("--job-credentials", default=os.getenv("AAP_JOB_CREDENTIALS", ""))
    result.add_argument("--skip-project-sync", action="store_true")
    return result


def main() -> None:
    configured = configure(parser().parse_args())
    print(
        f"AAP_CONFIGURED=project:{configured['project_name']}:"
        f"template:{configured['template_name']}"
    )


if __name__ == "__main__":
    main()
