from __future__ import annotations

import argparse
import pathlib

from awx_bootstrap import AwxApi, read_secret


TEMPLATES = (
    "WAS Base - Start Server and Discovered Applications",
    "WAS Base - Status and wsadmin Probe",
    "WAS Base - Deploy Sample Application",
    "WAS Base - Restart Sample Application",
    "WAS Base - Health Check",
    "WAS Base - Deploy Test EARs",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch and verify the genuine WebSphere Base AWX templates."
    )
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument(
        "--template",
        action="append",
        choices=TEMPLATES,
        help="Launch only this template; repeat the option to select more than one.",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    api = AwxApi(
        args.url,
        "admin",
        read_secret(root / ".secrets" / "awx_admin_password"),
    )
    api.authenticate()

    for name in args.template or TEMPLATES:
        template = api.find_one("/api/v2/job_templates/", name)
        if not template:
            raise RuntimeError(f"AWX Base template is missing: {name}")
        launched = api.request(
            "POST",
            f"/api/v2/job_templates/{template['id']}/launch/",
            json={},
        )
        job_url = launched.get("url") or f"/api/v2/jobs/{launched['id']}/"
        job = api.wait_job(job_url, timeout=900)
        print(f"AWX_BASE_JOB={name}:{job['id']}:{job['status']}")

    print("AWX_BASE_INTEGRATION=successful")


if __name__ == "__main__":
    main()
