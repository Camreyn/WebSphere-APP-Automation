# Configure the AAP wave-reboot job from GitHub

The manually dispatched GitHub Actions workflow
`.github/workflows/configure-aap-wave-reboot.yml` idempotently creates or
updates these Automation Controller resources:

1. the Git-backed project for this repository,
2. the `WAS - Reboot Nodes by Wave` job template,
3. its existing Machine and WebSphere credential associations, and
4. its guarded launch survey.

The workflow synchronizes the project before it updates the template. It does
not create inventories, credentials, or execution-environment images; those
remain separately governed platform resources.

## GitHub environment

Create a protected GitHub environment named `aap` (or set the repository
variable `AAP_GITHUB_ENVIRONMENT` to another name). Production approval rules
on that environment protect the controller token and the external mutation.

Add these environment secrets:

| Secret | Purpose |
|---|---|
| `AAP_HOST` | Automation Controller/AWX base URL, for example `https://aap.example.test` |
| `AAP_OAUTH_TOKEN` | OAuth token allowed to manage projects, templates, surveys, and credential associations |

Add these environment or repository variables:

| Variable | Required | Purpose |
|---|---:|---|
| `AAP_INVENTORY` | Yes | Existing inventory containing every application pair |
| `AAP_JOB_CREDENTIALS` | Yes | Comma-separated existing credential names, normally the Machine and WebSphere administrative credentials |
| `AAP_ORGANIZATION` | No | Organization name; defaults to `Default` |
| `AAP_EXECUTION_ENVIRONMENT` | No | Existing execution environment assigned to the template |
| `AAP_PROJECT_NAME` | No | Project-name override |
| `AAP_TEMPLATE_NAME` | No | Job-template-name override |
| `AAP_PROJECT_SCM_URL` | No | Git URL override; defaults to the current GitHub repository URL |
| `AAP_SCM_CREDENTIAL` | No | Existing source-control credential for a private repository |
| `AAP_API_PREFIX` | No | API route; defaults to `/api/v2`. Set the platform-gateway controller route when required by your AAP installation |
| `AAP_VALIDATE_CERTS` | No | `true`, `false`, or a CA-bundle path; defaults to `true` |
| `AAP_RUNNER` | No | Runner label; defaults to `ubuntu-latest`. Use a self-hosted label when AAP is private |

The controller must be reachable from the selected runner. For an internal AAP
installation, use a self-hosted runner with the necessary network route and CA
trust instead of disabling TLS verification.

## Inventory contract

For each pair, Node 2 is wave 1 and Node 1 is wave 2. Both hosts point at the
Node 1 Dmgr, and Node 1 declares that the Dmgr is co-located:

```yaml
was_nodes:
  hosts:
    app1_node2:
      was_maintenance_wave: 1
      was_maintenance_dmgr_host: app1_node1
      was_node_name: App1Node02
      was_cluster_name: App1Cluster
      was_server_name: server1
      was_maintenance_health_urls:
        - https://app1-node2.example.test/app1/health

    app1_node1:
      was_maintenance_wave: 2
      was_maintenance_hosts_dmgr: true
      was_maintenance_dmgr_host: app1_node1
      was_node_name: App1Node01
      was_cluster_name: App1Cluster
      was_server_name: server1
      was_maintenance_health_urls:
        - https://app1-node1.example.test/app1/health
```

Health URLs must address the named node directly. A shared load-balanced URL
can return success from the partner and falsely approve a failed recovery.
The playbook's default preflight requires every wave-2 host to declare
`was_maintenance_hosts_dmgr: true`, preventing an ungoverned Node 1 reboot that
relies on incidental Dmgr autostart.

## Run the setup job

Open **Actions → Configure AAP wave-reboot automation → Run workflow**. Select
the SCM branch that AAP should synchronize and optionally override the project
or template name.

The survey defaults reboot authorization to `false`. An operator must enable it
for an actual maintenance launch. The playbook then performs full preflight
before changing any host, runs every Node 2 host concurrently, and blocks Node
1 unless every Node 2 application passes direct health checks. Set the
controller/job fork capacity to at least the number of hosts in the larger wave
when every application must progress simultaneously.
