from __future__ import annotations

import argparse
import pathlib
import time
from urllib.parse import urljoin

import requests

from awx_bootstrap import AwxApi, read_secret


def stdout(api: AwxApi, job_id: int) -> str:
    response = api.session.get(
        urljoin(api.base_url, f"api/v2/jobs/{job_id}/stdout/?format=txt"),
        headers={"Accept": "text/plain"},
        timeout=90,
    )
    response.raise_for_status()
    return response.text


def launch(
    api: AwxApi,
    template_id: int,
    application: str,
    version: str,
    ticket: str,
    preflight_only: bool,
    expected_job_status: str = "successful",
) -> tuple[dict, str]:
    launched = api.request(
        "POST",
        f"/api/v2/job_templates/{template_id}/launch/",
        json={
            "extra_vars": {
                "deployment_application": application,
                "deployment_version": version,
                "change_ticket": ticket,
                "preflight_only": "true" if preflight_only else "false",
            }
        },
    )
    job_id = int(launched["id"])
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        job = api.request("GET", f"/api/v2/jobs/{job_id}/")
        if job.get("status") in {"successful", "failed", "error", "canceled"}:
            output = stdout(api, job_id)
            if job.get("status") != expected_job_status:
                raise RuntimeError(
                    f"AWX job {job_id} ended as {job.get('status')}, expected "
                    f"{expected_job_status}:\n{output[-16000:]}"
                )
            return job, output
        time.sleep(3)
    raise TimeoutError(f"AWX job {job_id} did not finish")


def require_report(job: dict, expected: str) -> dict:
    report = (job.get("artifacts") or {}).get("was_deployment_report")
    if not isinstance(report, dict):
        raise RuntimeError(f"AWX job {job['id']} did not publish was_deployment_report")
    if report.get("status") != expected:
        raise RuntimeError(
            f"AWX job {job['id']} report status was {report.get('status')}, expected {expected}"
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify the simple existing-application workflow through AWX."
    )
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument("--application", default="orders-test")
    parser.add_argument("--version", required=True)
    parser.add_argument("--ticket", default="LAB-OPERATOR-VERIFY")
    parser.add_argument("--health-url", default="http://127.0.0.1:9180/orders-test/")
    parser.add_argument(
        "--expected-deploy-status",
        choices=("SUCCESS", "NO_CHANGE"),
        default="SUCCESS",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    api = AwxApi(
        args.url,
        "admin",
        read_secret(root / ".secrets" / "awx_admin_password"),
    )
    api.authenticate()
    template = api.find_one(
        "/api/v2/job_templates/", "WAS - Update Existing Application"
    )
    if not template:
        raise RuntimeError("Simple existing-application AWX template is missing")

    preflight_job, preflight_stdout = launch(
        api,
        template["id"],
        args.application,
        args.version,
        args.ticket + "-PREFLIGHT",
        True,
    )
    require_report(preflight_job, "PREFLIGHT_OK")
    if "[4/8] Discover the application directly from the live WAS cell" not in preflight_stdout:
        raise RuntimeError("Preflight stdout did not contain the live-discovery progress step")
    print(f"AWX_PREFLIGHT_JOB={preflight_job['id']}:PREFLIGHT_OK")

    deploy_job, deploy_stdout = launch(
        api,
        template["id"],
        args.application,
        args.version,
        args.ticket,
        False,
    )
    deploy_report = require_report(deploy_job, args.expected_deploy_status)
    markers = ["AWX REPORT | Display the deployment-time WAS log excerpt"]
    if args.expected_deploy_status == "SUCCESS":
        markers.extend([
            "[5/8] Export the currently installed application for rollback",
            "[6/8] Update only the existing application archive",
        ])
    for marker in markers:
        if marker not in deploy_stdout:
            raise RuntimeError(f"Deployment stdout is missing progress marker: {marker}")
    response = requests.get(args.health_url, timeout=30)
    response.raise_for_status()
    if args.version not in response.text:
        raise RuntimeError("Updated endpoint does not display the requested release version")
    if not deploy_report.get("application_after", {}).get("running"):
        raise RuntimeError("Deployment report does not show the application running")
    print(
        f"AWX_DEPLOY_JOB={deploy_job['id']}:{args.expected_deploy_status}:"
        f"LOG_ERRORS={deploy_report['was_log_delta']['error_count']}"
    )

    repeat_job, _ = launch(
        api,
        template["id"],
        args.application,
        args.version,
        args.ticket + "-REPEAT",
        False,
    )
    require_report(repeat_job, "NO_CHANGE")
    print(f"AWX_REPEAT_JOB={repeat_job['id']}:NO_CHANGE")
    print("AWX_EXISTING_APPLICATION_INTEGRATION=successful")


if __name__ == "__main__":
    main()
