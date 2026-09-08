# Configure AAP from inside AAP

Import this repository as an AAP Project, create one small job template that
runs `setup.yml`, and launch it. That playbook calls AAP's own controller API
from inside AAP and idempotently creates or updates the operational template
and survey. No GitHub Action or external runner is involved.

## 1. Create the production inventory

Create an inventory with a `was_nodes` group. For the reboot workflow, maintain
only the inventory host identity and connection address:

```yaml
all:
  children:
    was_nodes:
      hosts:
        app1_node1:
          ansible_host: 10.20.1.11
        app1_node2:
          ansible_host: 10.20.1.12
        app2_node1:
          ansible_host: 10.20.2.11
        app2_node2:
          ansible_host: 10.20.2.12
```

Do not maintain cell, cluster, node, member, profile, Dmgr, SOAP-port, health,
or wave variables per server. The operational playbook discovers them from the
local profile files and live Dmgr. If WebSphere is outside the standard install
roots, define one inventory-group variable named
`was_maintenance_install_roots` containing the candidate root paths.
Standard discovery includes `/opt/WebSphere/AppServer`,
`/opt/WebSphere/AppServers`, conventional IBM WAS roots, plus versioned
`/opt/IBM/Workflow/*`, `/opt/ibm/Workflow/*`, `/opt/IBM/BPM/*`, and
`/opt/ibm/BPM/*` installations.

Profile names are not configuration inputs. Discovery enumerates the profile
registry and every directory beneath each installation's `profiles` folder.
Executable and configuration markers identify Dmgr and managed profiles first.
If those markers are incomplete, common names such as `AppSrv01`,
`AppServer02`, `Dmgr01`, or `dmgr` are recognized case-insensitively, followed
by guarded `app*` and `dm*` name-prefix fallbacks. A prefix is accepted only
when the directory also contains WebSphere profile metadata; live cell and
cluster-member correlation must still succeed before reboot authorization.

## 2. Import the Project

Create or update an Automation Controller Project:

- **Source control type:** Git
- **Source control URL:** this repository in your GitHub installation
- **Source control branch:** the branch to operate from, normally `main`
- **Update revision on launch:** enabled when setup should use the newest commit

Sync the Project and confirm that the root `setup.yml` is offered as a playbook.

## 3. Create the setup credential

Create a credential using AAP's built-in **Red Hat Ansible Automation Platform**
credential type. Point it at this AAP instance and use an OAuth token whose user
can read the setup template and create or update job templates and surveys in
the organization.

Keep TLS verification enabled with a trusted certificate. For an internal CA,
install that CA in the execution environment instead of disabling validation.

## 4. Create the one manual setup template

Create **WAS - Setup Automation** with:

| Setting | Value |
| --- | --- |
| Inventory | The production inventory from step 1 |
| Project | The imported Git Project |
| Playbook | `setup.yml` |
| Execution Environment | The EE intended for the operational job |
| Credentials | Only the AAP controller credential from step 3 |

The inventory is selected here so the generated template can inherit it.
`setup.yml` itself runs on localhost and does not SSH to the WebSphere hosts.
It does not need the Machine or WebSphere credentials.

## 5. Launch setup

Launch **WAS - Setup Automation**. It creates or updates **WAS - Reboot Nodes
by Wave**, its survey, native credential prompt, and native Forks prompt.

Rerun setup after syncing repository changes. Existing managed fields and the
survey are updated in place. Operational credentials are deliberately not
copied from the setup template and stale credential associations are removed.

## 6. Create the two operational credentials

Create a normal **Machine** credential that can connect to every inventory host,
use privilege escalation, and reboot it.

Create a protected WebSphere custom credential that injects exactly these extra
variables:

```yaml
was_admin_user: "{{ username }}"
was_admin_password: "{{ password }}"
```

The custom credential type should mark `password` secret. These credentials are
selected in AAP's native **Credentials** launch step; passwords are not survey
answers and are not stored in inventory or Git.

## 7. Launch the operational template

Launch **WAS - Reboot Nodes by Wave** and supply:

1. **Credentials:** select the Machine credential and WebSphere credential.
2. **Survey:** leave `was_nodes` unless using another host group, set the two
   timeouts, and set reboot authorization to `true` only for an approved run.
3. **Forks:** enter at least the number of application pairs. For five pairs,
   enter at least `5`, so all five Node 2 hosts can run together and then all
   five Node 1 hosts can run together.

Leaving authorization at its default `false` performs complete read-only
discovery, prints the proposed pairs and waves, and stops before any shutdown.

## What the job discovers and enforces

Before changing a host, the job:

- finds the registered Dmgr and managed-node profiles, install roots, profile
  names, owning OS users, cells, nodes, local servers, and Dmgr SOAP ports;
- reads `versionInfo.sh` and the profile-local `wsadmin.sh` runtime to identify
  WAS, legacy IBM BPM, or BAW, the underlying WAS version, and Jython 2.1 or
  2.7 without inventory flags;
- queries every Dmgr for live clusters, members, member states, applications,
  and application runtime placement;
- requires exactly two managed hosts per cell and exactly one co-located Dmgr;
- defines the Dmgr host as Node 1/wave 2 and its partner as Node 2/wave 1;
- rejects stopped members, missing hosts, ambiguous profiles, incomplete pairs,
  or too few Ansible forks before the first disruptive task.

Wave 1 stops and reboots all Node 2 hosts concurrently. Each must reconnect,
restart its node agent and members, and restore every application runtime that
was present before maintenance. Only then can wave 2 start. On every Node 1
host, the job stops the co-located Dmgr last and starts it first before
recovering that node's members and applications.

The default health gate is live WebSphere member state plus restoration of each
pre-maintenance application runtime instance. Optional direct HTTP checks can
still be supplied as group/host variables in `was_maintenance_health_urls`; set
`was_maintenance_require_health_checks: true` only when those URLs are required.
For BAW/BPM this automatically covers its WebSphere cluster members and all
running deployed application MBeans. It does not claim that a process engine,
database-dependent workflow, or business transaction completed; use optional
HTTP checks when that deeper functional proof is required.

## Supported topology and safety boundary

Automatic pairing intentionally fails closed unless each selected cell has:

- exactly two inventory hosts with one managed profile on each;
- exactly one Dmgr profile, co-located with the host designated Node 1;
- clustered managed servers visible and started in the live Dmgr;
- profile paths readable under privilege escalation.

The collection's built-in wsadmin bridge deliberately uses the Jython 2.1
language subset, so the same job supports the Jython 2.1 runtime shipped with
WAS 8.5.5 and the Jython 2.7 runtime normally used by WAS 9. The detected
generation and product family appear in the read-only plan. Any other Jython
generation or unidentified product fails preflight before shutdown.

If a cell uses a separate Dmgr host, more than two managed nodes, multiple
managed profiles per OS host, or another layout, do not use this two-wave job
without extending its discovery policy for that topology.

Restrict launch access to the setup template because its AAP credential can
change controller configuration. `controller_api_prefix` can be supplied as an
extra variable only if automatic discovery cannot choose between
`/api/controller/v2` and `/api/v2`.
