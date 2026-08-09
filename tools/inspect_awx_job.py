from __future__ import annotations

import argparse
import pathlib

from awx_bootstrap import AwxApi, read_secret


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a concise local AWX job artifact summary.")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument("--job-id", type=int, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    api = AwxApi(
        args.url,
        "admin",
        read_secret(root / ".secrets" / "awx_admin_password"),
    )
    api.authenticate()
    job = api.request("GET", f"/api/v2/jobs/{args.job_id}/")
    artifacts = job.get("artifacts") or {}
    print(f"AWX_JOB={job['id']}:{job.get('status')}:{job.get('name')}")
    print("ARTIFACT_KEYS=" + ",".join(sorted(artifacts)))

    applications = artifacts.get("was_discovered_applications") or []
    rows = artifacts.get("was_application_start_rows") or []
    if applications:
        running = sum(
            1 for row in rows
            if row.get("after_running") and not row.get("failed")
        )
        print("DISCOVERED_APPLICATIONS=" + ",".join(applications))
        print(f"RUNNING_APPLICATIONS={running}/{len(rows)}")

    report = artifacts.get("was_deployment_report")
    if isinstance(report, dict):
        print(f"DEPLOYMENT_STATUS={report.get('status')}")
        print(f"DEPLOYMENT_APPLICATION={report.get('application')}")
        print(f"DEPLOYMENT_VERSION={report.get('version')}")
        log_delta = report.get("was_log_delta") or {}
        line_count = sum(len(item.get("lines") or []) for item in log_delta.get("files") or [])
        print(f"WAS_LOG_LINES={line_count}")
        print(f"WAS_LOG_WARNINGS={log_delta.get('warning_count', 0)}")
        print(f"WAS_LOG_ERRORS={log_delta.get('error_count', 0)}")


if __name__ == "__main__":
    main()
