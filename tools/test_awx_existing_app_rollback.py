from __future__ import annotations

import argparse
import pathlib

import requests

from awx_bootstrap import AwxApi, read_secret
from test_awx_existing_app import launch, require_report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prove exported-EAR rollback for the simple AWX deployment job."
    )
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument("--application", default="orders-test")
    parser.add_argument("--rejected-version", required=True)
    parser.add_argument("--stable-version", required=True)
    parser.add_argument("--ticket", default="LAB-ROLLBACK-VERIFY")
    parser.add_argument("--health-url", default="http://127.0.0.1:9180/orders-test/")
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

    job, output = launch(
        api,
        template["id"],
        args.application,
        args.rejected_version,
        args.ticket,
        False,
        expected_job_status="failed",
    )
    report = require_report(job, "FAILED_ROLLED_BACK")
    if report.get("rollback") != "successful":
        raise RuntimeError("AWX report does not identify a successful rollback")
    if "ROLLBACK | Mark automatic recovery successful" not in output:
        raise RuntimeError("AWX output is missing the successful rollback progress step")
    response = requests.get(args.health_url, timeout=30)
    response.raise_for_status()
    if args.stable_version not in response.text:
        raise RuntimeError("Endpoint did not return to the stable release after rollback")
    if args.rejected_version in response.text:
        raise RuntimeError("Rejected release is still visible after rollback")
    print(
        f"AWX_ROLLBACK_JOB={job['id']}:FAILED_ROLLED_BACK:"
        f"ORIGINAL_STEP={report['error'].get('task', 'unknown')}"
    )
    print("AWX_EXISTING_APPLICATION_ROLLBACK=successful")


if __name__ == "__main__":
    main()
