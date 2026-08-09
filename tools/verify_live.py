from __future__ import annotations

import argparse
import json
import pathlib
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Callable

import requests


@dataclass
class Check:
    name: str
    status: str
    detail: str


LAN_PORTS = {
    2220, 2221, 2222, 2230, 8080, 8404, 8879, 8880, 8888, 9043, 9060,
    9081, 9082, 9143, 9160, 9180, 9418, 9444, 9445, 9543, 32000,
}


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def run(command: list[str], root: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )


def add(checks: list[Check], name: str, probe: Callable[[], str], absent_ok: bool = False) -> None:
    try:
        detail = probe()
        checks.append(Check(name, "pass", detail))
    except FileNotFoundError as exc:
        checks.append(Check(name, "skip" if absent_ok else "fail", str(exc)))
    except Exception as exc:  # each check reports independently
        checks.append(Check(name, "fail", str(exc)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Non-destructive live verification for the lab.")
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--require-awx", action="store_true")
    parser.add_argument("--require-was", action="store_true")
    parser.add_argument("--require-base", action="store_true")
    parser.add_argument(
        "--exercise-release-reporting",
        action="store_true",
        help="Launch the media-independent AWX rejection reporter and verify its artifacts.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    checks: list[Check] = []

    def check_portal() -> str:
        if not port_open(8888):
            raise RuntimeError("portal port 8888 is closed")
        response = requests.get("http://127.0.0.1:8888/", timeout=10)
        response.raise_for_status()
        if "HIGH-CHARITY Lab Hub" not in response.text:
            raise RuntimeError("unexpected portal response")
        return f"HTTP {response.status_code} on desktop-local port 8888"

    add(checks, "Lab portal", check_portal)

    def check_scm() -> str:
        if not port_open(9418):
            raise FileNotFoundError("SCM service is not running")
        result = run(["git", "ls-remote", "git://127.0.0.1:9418/was-lab.git", "HEAD"], root)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "git ls-remote failed")
        return result.stdout.split()[0]

    add(checks, "Local Git project", check_scm, absent_ok=True)

    def check_awx() -> str:
        if not port_open(32000):
            if args.require_awx:
                raise RuntimeError("AWX port 32000 is closed")
            raise FileNotFoundError("AWX is not running")
        response = requests.get("http://127.0.0.1:32000/api/v2/ping/", timeout=10)
        response.raise_for_status()
        version = response.json().get("version", "unknown")
        if version != "24.6.1":
            raise RuntimeError(f"expected AWX 24.6.1, received {version}")
        return f"AWX {version}"

    add(checks, "AWX API", check_awx, absent_ok=not args.require_awx)

    if port_open(32000):
        def check_awx_release_workflow() -> str:
            # Import locally so basic portal/SCM checks remain usable before the
            # bootstrap dependencies or AWX itself have been installed.
            from awx_bootstrap import AwxApi

            password_path = root / ".secrets" / "awx_admin_password"
            password = password_path.read_text(encoding="utf-8").strip()
            if not password:
                raise RuntimeError("AWX administrator password is empty")
            api = AwxApi("http://127.0.0.1:32000", "admin", password)
            api.authenticate()
            workflow = api.find_one(
                "/api/v2/workflow_job_templates/",
                "WAS - Deploy Clustered EAR",
            )
            if not workflow:
                raise RuntimeError("clustered EAR workflow is missing")
            deployment_template = api.find_one(
                "/api/v2/job_templates/",
                "WAS EAR Release - Deploy",
            )
            if not deployment_template:
                raise RuntimeError("clustered EAR deployment phase is missing")
            if deployment_template.get("allow_simultaneous"):
                raise RuntimeError("Dmgr application updates are not serialized")

            survey = api.request("GET", workflow["url"].rstrip("/") + "/survey_spec/")
            variables = {
                question.get("variable") for question in survey.get("spec", [])
            }
            expected_variables = {
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
                "release_notes",
            }
            if variables != expected_variables:
                raise RuntimeError(
                    f"release survey mismatch; missing={sorted(expected_variables - variables)}, "
                    f"unexpected={sorted(variables - expected_variables)}"
                )

            payload = api.request(
                "GET",
                f"/api/v2/workflow_job_templates/{workflow['id']}/workflow_nodes/",
            )
            nodes = {node.get("identifier"): node for node in payload.get("results", [])}
            expected_nodes = {
                "validate-immutable-release",
                "operations-approval",
                "deploy-and-verify",
                "report-approval-rejected",
            }
            if set(nodes) != expected_nodes:
                raise RuntimeError(
                    f"release node mismatch; expected={sorted(expected_nodes)}, "
                    f"actual={sorted(nodes)}"
                )
            approval = nodes["operations-approval"]
            if not approval.get("unified_job_template"):
                raise RuntimeError("AWX approval template is not attached to its node")

            def edge_ids(identifier: str, edge: str) -> set[int]:
                node = nodes[identifier]
                children = api.request(
                    "GET",
                    f"/api/v2/workflow_job_template_nodes/{node['id']}/{edge}/",
                )
                return {int(child["id"]) for child in children.get("results", [])}

            if nodes["operations-approval"]["id"] not in edge_ids(
                "validate-immutable-release", "success_nodes"
            ):
                raise RuntimeError("validation success is not connected to approval")
            if nodes["deploy-and-verify"]["id"] not in edge_ids(
                "operations-approval", "success_nodes"
            ):
                raise RuntimeError("approval success is not connected to deployment")
            if nodes["report-approval-rejected"]["id"] not in edge_ids(
                "operations-approval", "failure_nodes"
            ):
                raise RuntimeError("approval failure is not connected to reporting")
            detail = (
                f"workflow {workflow['id']} with {len(variables)} survey fields, "
                "native approval, serialized deploy, and rejection branches"
            )
            if args.exercise_release_reporting:
                reporter = api.find_one(
                    "/api/v2/job_templates/",
                    "WAS EAR Release - Approval Rejected",
                )
                if not reporter:
                    raise RuntimeError("approval rejection reporting template is missing")
                launched = api.request(
                    "POST",
                    f"/api/v2/job_templates/{reporter['id']}/launch/",
                    json={
                        "extra_vars": {
                            "deployment_application": "was-lab",
                            "deployment_version": "lab-1",
                            "deployment_sha256": "0" * 64,
                            "change_ticket": "AWX-REPORT-SELFTEST",
                            "requested_by": "tools/verify_live.py",
                            "notification_email_to": "",
                            "deployment_strategy": "maintenance",
                            "auto_rollback": True,
                            "force_deploy": False,
                            "send_email": False,
                            "release_notes": "Media-independent live AWX artifact test",
                        }
                    },
                )
                job_url = launched.get("url") or f"/api/v2/jobs/{launched['id']}/"
                completed = api.wait_job(job_url)
                artifacts = completed.get("artifacts") or {}
                if artifacts.get("was_release_status") != "NOT_DEPLOYED":
                    raise RuntimeError(
                        f"unexpected reporting artifact status: {artifacts}"
                    )
                report = artifacts.get("was_release_report", "")
                if "AWX-REPORT-SELFTEST" not in report or "NOT_DEPLOYED" not in report:
                    raise RuntimeError("verbose release report is absent from AWX artifacts")
                email = artifacts.get("was_release_email") or {}
                if email.get("attempted") or email.get("delivered"):
                    raise RuntimeError(f"disabled self-test email was unexpectedly sent: {email}")
                detail += f"; reporting job {completed['id']} artifacts verified"
            return detail

        add(checks, "AWX clustered release workflow", check_awx_release_workflow)

    lan_state_path = root / ".data" / "lan-access.json"
    if lan_state_path.exists():
        lan_state = json.loads(lan_state_path.read_text(encoding="utf-8-sig"))
        lan_address = str(lan_state["listen_address"])
        configured_ports = {int(port) for port in lan_state.get("ports", [])}

        def check_lan_configuration() -> str:
            if configured_ports != LAN_PORTS:
                missing = sorted(LAN_PORTS - configured_ports)
                unexpected = sorted(configured_ports - LAN_PORTS)
                raise RuntimeError(f"port-set mismatch; missing={missing}, unexpected={unexpected}")
            response = requests.get(f"http://{lan_address}:8888/", timeout=10)
            response.raise_for_status()
            if "HIGH-CHARITY Lab Hub" not in response.text:
                raise RuntimeError("unexpected portal response through LAN address")
            return f"portal reachable directly at http://{lan_address}:8888/"

        add(checks, "Trusted-LAN Docker gateway", check_lan_configuration)

        if port_open(32000):
            def check_lan_awx() -> str:
                response = requests.get(f"http://{lan_address}:32000/api/v2/ping/", timeout=10)
                response.raise_for_status()
                return f"AWX {response.json().get('version', 'unknown')} via desktop IP"

            add(checks, "Trusted-LAN AWX API", check_lan_awx)

        if port_open(9418):
            def check_lan_scm() -> str:
                result = run(["git", "ls-remote", f"git://{lan_address}:9418/was-lab.git", "HEAD"], root)
                if result.returncode:
                    raise RuntimeError(result.stderr.strip() or "LAN git ls-remote failed")
                return result.stdout.split()[0]

            add(checks, "Trusted-LAN Git project", check_lan_scm)

        if port_open(9180):
            def check_lan_base() -> str:
                required_ports = (2230, 8880, 9143, 9160, 9180, 9543)
                closed = [port for port in required_ports if not port_open(port, lan_address)]
                if closed:
                    raise RuntimeError(f"Base LAN gateway ports are closed: {closed}")
                response = requests.get(
                    f"http://{lan_address}:9180/was-lab-base/",
                    timeout=10,
                )
                response.raise_for_status()
                if "WebSphere Base 9 Lab" not in response.text:
                    raise RuntimeError("unexpected Base response through LAN gateway")
                return f"Base app and six TCP endpoints reachable via {lan_address}"

            add(checks, "Trusted-LAN WebSphere Base", check_lan_base)
    else:
        checks.append(Check("Trusted-LAN Docker gateway", "skip", "run .\\lab.ps1 lan-up to enable"))

    def check_was() -> str:
        inspect = run(
            [
                "docker",
                "--context",
                "desktop-linux",
                "inspect",
                "-f",
                "{{.State.Running}}",
                "wasnd-lab-dmgr",
            ],
            root,
        )
        if inspect.returncode or inspect.stdout.strip() != "true":
            if args.require_was:
                raise RuntimeError("WAS deployment manager is not running")
            raise FileNotFoundError("WAS is not running; authorized IBM media may be pending")
        result = run(
            [
                "docker",
                "--context",
                "desktop-linux",
                "exec",
                "wasnd-lab-dmgr",
                "bash",
                "-lc",
                "/opt/WebSphere/AppServers/bin/versionInfo.sh && "
                "test -x /opt/WebSphere/AppServers/profiles/Dmgr01/bin/wsadmin.sh",
            ],
            root,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            raise RuntimeError(output.strip())
        if "Network Deployment" not in output or "9.0.5.28" not in output:
            raise RuntimeError("container is not verified as WebSphere ND 9.0.5.28")
        return "genuine ND 9.0.5.28 and Dmgr01/bin/wsadmin.sh verified"

    add(checks, "WebSphere runtime", check_was, absent_ok=not args.require_was)

    def check_was_base() -> str:
        inspect = run(
            [
                "docker", "--context", "desktop-linux", "inspect", "-f",
                "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
                "wasnd-lab-base",
            ],
            root,
        )
        if inspect.returncode or not inspect.stdout.strip().startswith("true"):
            if args.require_base:
                raise RuntimeError("WebSphere Base ILAN is not running")
            raise FileNotFoundError("WebSphere Base ILAN is not running")
        if "healthy" not in inspect.stdout:
            raise RuntimeError(f"WebSphere Base is not healthy: {inspect.stdout.strip()}")
        result = run(
            [
                "docker", "--context", "desktop-linux", "exec", "wasnd-lab-base",
                "bash", "-lc",
                "/opt/IBM/WebSphere/AppServer/bin/versionInfo.sh -ifixes && "
                "test -x /opt/IBM/WebSphere/AppServer/profiles/AppSrv01/bin/wsadmin.sh",
            ],
            root,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            raise RuntimeError(output.strip())
        if "ID                    BASE" not in output or "9.0.5.28" not in output:
            raise RuntimeError("container is not verified as WebSphere traditional Base 9.0.5.28")
        return "official IBM Base 9.0.5.28 and AppSrv01/bin/wsadmin.sh verified"

    add(checks, "WebSphere Base ILAN runtime", check_was_base, absent_ok=not args.require_base)

    if port_open(9180):
        def check_base_application() -> str:
            response = requests.get("http://127.0.0.1:9180/was-lab-base/", timeout=10)
            response.raise_for_status()
            if "WebSphere Base 9 Lab" not in response.text:
                raise RuntimeError("unexpected Base application response")
            return f"HTTP {response.status_code} from genuine WebSphere Base"

        add(checks, "WebSphere Base sample application", check_base_application)
    else:
        checks.append(Check("WebSphere Base sample application", "skip", "Base port 9180 is closed"))

    if port_open(8080):
        def check_application() -> str:
            response = requests.get("http://127.0.0.1:8080/was-lab/", timeout=10)
            response.raise_for_status()
            if "WebSphere ND 9 Cluster Lab" not in response.text:
                raise RuntimeError("unexpected application response")
            return f"HTTP {response.status_code} through HAProxy"

        add(checks, "Cluster application", check_application)
    else:
        checks.append(Check("Cluster application", "skip", "HAProxy is not running"))

    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        for check in checks:
            print(f"{check.status.upper():4} {check.name}: {check.detail}")

    if any(check.status == "fail" for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
