# Using the `waslab.wasnd` collection

This guide covers collection version `0.1.0`. The collection manages
traditional IBM WebSphere Application Server Network Deployment 9. Its
information, application, and custom-Jython operations also support
traditional WebSphere Base. It does not manage Liberty, emulate WebSphere, or
contain IBM software.

There are three common ways to use it:

- Operate an existing cell. Install the collection on the Ansible controller,
  target the deployment-manager host, and use the wsadmin-backed modules for
  clusters, members, applications, JVM settings, synchronization, and status.
- Build a new cell. Make licensed IBM repositories available on each managed
  host, then apply the install, deployment-manager, managed-node, and cell
  roles in that order.
- Exercise genuine administrative and application behavior on a stand-alone
  Base profile. Cluster and federation modules are not applicable in that mode.

## How the connection works

Ansible connects to a RHEL-compatible host over SSH and transfers a normal
Python module. For administrative operations, that module invokes the genuine
profile script on the managed host:

```text
Ansible controller
  -> SSH to the deployment-manager operating-system host
  -> /opt/WebSphere/AppServers/profiles/Dmgr01/bin/wsadmin.sh
  -> SOAP connector on localhost:8879
  -> WebSphere cell configuration and runtime MBeans
```

The `federation` module is the exception: it runs on an application-node host
and calls that profile's `addNode.sh` or `removeNode.sh` against the Dmgr SOAP
endpoint.

For the supplied Base ILAN target, the equivalent path is:

```text
Ansible controller
  -> SSH to was-base
  -> /opt/IBM/WebSphere/AppServer/profiles/AppSrv01/bin/wsadmin.sh
  -> SOAP connector on localhost:8880
  -> DefaultCell01 / DefaultNode01 / server1
```

## Requirements

Controller requirements:

- `ansible-core` 2.15 or newer.
- SSH access to the managed operating-system hosts.
- An execution environment containing the standard Ansible Python runtime.

Managed-host requirements:

- RHEL 9 or a compatible Linux environment with Python 3 for Ansible modules.
- A service account, `was` by default, that owns or can operate WebSphere.
- For existing-cell operations, a genuine traditional WAS Base or ND installation and
  profile-local `wsadmin.sh` and `PropFilePasswordEncoder.sh` scripts.
- Network access from managed nodes to the Dmgr SOAP port during federation.

New installations additionally require entitled IBM Installation Manager,
WAS ND, Java, and fix-pack repositories already mounted on the managed host.
The collection never downloads IBM media.

## Install the collection

### Use the source embedded in this project

The lab keeps the collection at:

```text
ansible/collections/ansible_collections/waslab/wasnd
```

Its `ansible/ansible.cfg` contains:

```ini
[defaults]
collections_path = collections
```

Run playbooks from `ansible/` or set `ANSIBLE_CONFIG` to that file. No Galaxy
download is required.

### Install the offline artifact

Build the artifact from the repository root:

```powershell
.\lab.ps1 collection-build
```

Install the resulting tarball into a standalone project:

```bash
ansible-galaxy collection install \
  ./ansible/dist/waslab-wasnd-0.1.0.tar.gz \
  --collections-path ./collections
```

Point Ansible at that directory:

```ini
[defaults]
collections_path = ./collections
```

Confirm discovery and inspect the authoritative module documentation:

```bash
ansible-galaxy collection list waslab.wasnd
ansible-doc waslab.wasnd.cell_info
ansible-doc waslab.wasnd.application
```

## Inventory model

The lifecycle roles expect three groups: `was_hosts`, `was_dmgr`, and
`was_nodes`. A conventional inventory looks like this:

```yaml
---
all:
  vars:
    ansible_user: ansible
    ansible_python_interpreter: /usr/bin/python3
    was_install_root: /opt/WebSphere/AppServers
    was_admin_user: wsadmin
    was_cell_name: LabCell01
    was_cluster_name: AppCluster01

  children:
    was_hosts:
      children:
        was_dmgr:
        was_nodes:

    was_dmgr:
      hosts:
        dmgr01.example.test:
          was_dmgr_host_name: dmgr01.example.test

    was_nodes:
      vars:
        was_dmgr_host: dmgr01.example.test
      hosts:
        app01.example.test:
          was_node_name: Node01
          was_node_host_name: app01.example.test
        app02.example.test:
          was_node_name: Node02
          was_node_host_name: app02.example.test
```

For operational modules, only the Dmgr host is required because its
`wsadmin.sh` administers the cell. Target the application hosts as well when
installing WebSphere, creating/federating profiles, or collecting their logs.

Run WebSphere-owned commands as the service account. The examples use:

```yaml
become: true
become_user: was
```

The connecting account therefore needs a suitable sudo policy. Installation
and operating-system package tasks require root privileges.

## Supply credentials safely

The common administrative variables are:

```yaml
was_admin_user: wsadmin
was_admin_password: "{{ vault_was_admin_password }}"
```

Keep the password in Ansible Vault, an AWX credential, or another secret
backend. Do not put it directly in inventory or source control. For example:

```bash
ansible-vault create inventory/group_vars/all/vault.yml
ansible-playbook playbooks/status.yml --ask-vault-pass
```

The collection declares password arguments with `no_log`. For each wsadmin
operation it creates a mode-0600 temporary SOAP properties copy, runs IBM's
`PropFilePasswordEncoder.sh`, uses that encoded file with `wsadmin.sh`, and
deletes it afterward. Passwords are not placed on the wsadmin command line.

In AWX, create a credential type whose injector supplies these extra variables:

```yaml
extra_vars:
  was_admin_user: "{{ username }}"
  was_admin_password: "{{ password }}"
```

The local lab creates this as the `WebSphere Administrative Credential` type
and attaches a credential named `WAS Lab wsadmin` to each operational job
template.

## Common wsadmin connection settings

The wsadmin-backed modules share the `group/waslab.wasnd.wasnd` action group.
Use `module_defaults` once at play level:

```yaml
module_defaults:
  group/waslab.wasnd.wasnd:
    install_root: /opt/WebSphere/AppServers
    profile_name: Dmgr01
    host: localhost
    port: 8879
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
    timeout: 300
```

| Setting | Default | Meaning |
|---|---:|---|
| `install_root` | `/opt/WebSphere/AppServers` | Traditional WAS installation root |
| `profile_name` | `Dmgr01` | Profile whose `bin/wsadmin.sh` is invoked |
| `wsadmin_path` | Derived | Optional explicit path to genuine `wsadmin.sh` |
| `host` | `localhost` | SOAP host as seen from the managed host |
| `port` | `8879` | Dmgr SOAP connector port |
| `username` | Required | WebSphere administrative identity |
| `password` | Required | Protected WebSphere password |
| `timeout` | `300` | Maximum command time in seconds |

Use the Dmgr profile for cell-level configuration. A `host` value such as a
laptop IP is normally wrong when the module itself is executing on the Dmgr
host; `localhost` is correct for the typical layout.

## Use the official Base ILAN lab target

From the project root, start IBM's pinned traditional WebSphere Base image and
run the real integration suite:

```powershell
.\lab.ps1 was-base-up
.\lab.ps1 collection-base-integration
```

The Base inventory is `ansible/inventory/base.yml`. Its module defaults differ
from the ND Dmgr defaults:

```yaml
module_defaults:
  group/waslab.wasnd.wasnd:
    install_root: /opt/IBM/WebSphere/AppServer
    profile_name: AppSrv01
    host: localhost
    port: 8880
    username: "{{ was_admin_user }}"
    password: "{{ was_admin_password }}"
```

`was_base_status.yml` verifies offering `BASE` at 9.0.5.28 and transfers a
custom Jython probe to genuine `AppSrv01/bin/wsadmin.sh`.
`was_base_deploy_sample.yml` installs and starts a WAR, while
`was_base_healthcheck.yml` requests it over HTTP. The integration harness runs
the deployment twice and requires the second application operation to report
no change. Use these Base-compatible modules for a stand-alone server:

- `cell_info`
- `application`
- `application_info`
- `application_export`
- `log_delta`
- `wsadmin`

The ND-only topology operations—`cluster`, `cluster_member`, `node_sync`,
`federation`, Dmgr lifecycle roles, and rolling cluster restart—cannot be
validated with Base.

## Operate an existing cell

### Inspect the cell

```yaml
---
- name: Read the WebSphere cell
  hosts: was_dmgr
  gather_facts: false
  become: true
  become_user: was
  module_defaults:
    group/waslab.wasnd.wasnd:
      install_root: "{{ was_install_root }}"
      profile_name: Dmgr01
      username: "{{ was_admin_user }}"
      password: "{{ was_admin_password }}"
  tasks:
    - name: Gather product and topology data
      waslab.wasnd.cell_info:
      register: was_cell

    - name: Show the structured result
      ansible.builtin.debug:
        var: was_cell.facts
```

`cell_info` returns product edition/version, cell name, nodes, servers,
clusters, cluster members, and installed applications.

Use `profile_runtime` to start a profile before connecting with `wsadmin`:

```yaml
- name: Ensure the stand-alone application server is running
  waslab.wasnd.profile_runtime:
    profile_type: application_server
    server_name: server1
    state: started
```

### Start or stop a cluster

```yaml
- name: Ensure the application cluster is running
  waslab.wasnd.cluster:
    name: AppCluster01
    state: started
```

Valid states are `present`, `started`, `stopped`, and guarded `absent`.

### Manage one cluster member

```yaml
- name: Restart one member
  waslab.wasnd.cluster_member:
    cluster: AppCluster01
    node: Node01
    name: server1
    state: restarted
```

Creation also supports `weight` and `generate_unique_ports`.

### Synchronize managed nodes

```yaml
- name: Synchronize selected nodes
  waslab.wasnd.node_sync:
    nodes:
      - Node01
      - Node02
```

An empty `nodes` list selects every managed node. A node agent must be running
for its NodeSync MBean to be available.

### Change JVM heap settings

```yaml
- name: Configure every member in the cluster
  waslab.wasnd.jvm_heap:
    cluster: AppCluster01
    initial_heap_mb: 512
    maximum_heap_mb: 2048
  register: heap_change
```

The initial heap cannot exceed the maximum. The module updates the JVM
configuration for every cluster member; use a rolling restart afterward to
activate configuration changes that require a process restart.

### Deploy or update an application

The `application` module expects `src` to be a path on the Dmgr operating-system
host. Stage controller-local WAR/EAR content first:

```yaml
- name: Deploy payroll.war
  hosts: was_dmgr
  gather_facts: false
  become: true
  become_user: was
  module_defaults:
    group/waslab.wasnd.wasnd:
      install_root: /opt/WebSphere/AppServers
      profile_name: Dmgr01
      username: "{{ was_admin_user }}"
      password: "{{ was_admin_password }}"
  tasks:
    - name: Stage the archive
      ansible.builtin.copy:
        src: files/payroll.war
        dest: /var/tmp/payroll.war
        mode: "0640"

    - name: Install or checksum-update the application
      waslab.wasnd.application:
        name: payroll
        src: /var/tmp/payroll.war
        cluster: AppCluster01
        context_root: /payroll
        virtual_host: default_host
        state: present
      notify: Synchronize WebSphere nodes

  handlers:
    - name: Synchronize WebSphere nodes
      waslab.wasnd.node_sync:
        nodes: []
```

The module records the archive SHA-256 in
`/var/lib/waslab/wasnd/application-checksums.json`. An unchanged checksum is
idempotent; set `force: true` to update regardless of the ledger.
For new installs, `virtual_host` defaults to `default_host` and the module uses
IBM's default-binding options so web modules do not stop at the interactive
`MapWebModToVH` task. Override it when the application uses a different
WebSphere virtual host, or pass an empty value only when the archive supplies
all required bindings.

Application runtime states can be managed separately:

```yaml
- name: Start the installed application
  waslab.wasnd.application:
    name: payroll
    state: started
```

### Perform a rolling restart

```yaml
- name: Restart cluster members one at a time
  hosts: was_dmgr
  gather_facts: false
  become: true
  become_user: was
  roles:
    - role: waslab.wasnd.rolling_restart
      vars:
        was_cluster_name: AppCluster01
        was_cluster_members:
          - node: Node01
            name: server1
          - node: Node02
            name: server1
        was_rolling_health_url: https://app.example.test/health
```

The role restarts members in the listed order. When a health URL is supplied,
it waits for HTTP 200 before advancing to the next member.

### Reboot two-node application pairs by wave

Use `playbooks/was_wave_reboot.yml` when several independent applications each
have a Node 1/Node 2 pair and the Dmgr is co-located on Node 1. It runs every
Node 2 host concurrently while the Dmgrs remain online, waits for all of them
to finish their complete maintenance sequence, and only then runs every Node 1
host concurrently. A failed Node 2 recovery blocks all Node 1 work.

Inventory contains only the hosts and their connection addresses:

```yaml
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

The playbook discovers registered profiles and their owners, then queries each
Dmgr for its live cell, clusters, server members, and applications. It requires
exactly two managed hosts per cell and exactly one Dmgr co-located on one of
them. The Dmgr host becomes Node 1/wave 2 automatically; the partner becomes
Node 2/wave 1. It also records every currently running application instance so
the same node/server placement must return after reboot.

Local discovery checks singular and plural `/opt/WebSphere/AppServer(s)` roots,
conventional IBM WAS roots, and versioned Workflow/BPM roots. It enumerates
registered and on-disk profile names rather than assuming `Dmgr01` or
`AppSrv01`. Profile scripts and configuration are authoritative; common names
and guarded `app*`/`dm*` directory prefixes are used only as fallbacks when the
directory contains WebSphere profile metadata.

Discovery also reads `versionInfo.sh` and asks the profile-local wsadmin runtime
for its Jython generation. It classifies plain WAS, legacy IBM BPM, and BAW
without per-server version flags. The built-in bridge uses syntax shared by
Jython 2.1 (WAS 8.5.5) and Jython 2.7 (the normal WAS 9 runtime); any unknown
product or untested Jython generation is rejected during read-only preflight.

Authorize the disruptive action only for the intended run:

```bash
ansible-playbook playbooks/was_wave_reboot.yml \
  -e was_maintenance_allow_reboot=true
```

The role stops each discovered managed server, stops the node agent, reboots,
starts the runtime, and verifies member state plus each pre-maintenance
application runtime. On Node 1 it stops Dmgr last, starts it first, and waits for
SOAP before using wsadmin. Optional direct URLs in
`was_maintenance_health_urls` add an HTTP gate; they are not required for the
default WebSphere runtime-health policy. Configure AAP Forks to at least the
number of hosts in the larger wave. Preflight fails before shutdown when the
topology is ambiguous, a member is down, or the fork count is insufficient.
On BAW/BPM, this policy verifies WebSphere members and every application MBean
that was running on the node before maintenance. Add an HTTP health endpoint if
the change requires proof of process-engine, database, or transaction health.
Integrate load-balancer drain and return-to-service controls around the role
when the production load balancer does not remove a stopped member automatically.

### Collect profile logs

```yaml
- name: Collect node logs
  hosts: was_nodes
  gather_facts: false
  roles:
    - role: waslab.wasnd.collect_logs
      vars:
        was_profile_name: AppSrv01
        was_log_destination: /srv/ansible-artifacts/websphere-logs/
```

The role creates a temporary archive on each host, fetches it, and removes the
remote archive. In AWX, the default destination uses the job artifact area when
`AWX_ISOLATED_DATA_DIR` is defined.

## Run custom Jython through genuine wsadmin

Use `waslab.wasnd.wsadmin` when a needed administrative operation is not yet a
first-class module. The action plugin transfers a controller-local script to a
temporary remote directory and removes it after execution:

```yaml
- name: Run a read-only custom report
  waslab.wasnd.wsadmin:
    src: files/custom_report.py
    args:
      - AppCluster01
    changed: false
  register: custom_report
```

Set `remote_src: true` when `src` is already on the managed host. A script can
return structured data by printing exactly one JSON marker line:

```python
from __future__ import print_function

import json

clusters = [item for item in AdminConfig.list("ServerCluster").splitlines() if item]
print("ANSIBLE_WAS_RESULT=" + json.dumps({
    "changed": False,
    "clusters": clusters,
}, sort_keys=True))
```

The dictionary is returned as `result`. If it contains `changed`, that value
overrides the module's `changed` fallback. The generic module intentionally
does not support check mode because arbitrary Jython cannot be predicted.

## Provision a new cell

### Prepare licensed media

Place or mount the following below `/was855` on every target host:

```text
/was855/
|-- agent.installer.linux.gtk.x86_64_1.9.x.zip
`-- repositories/
    |-- was-nd-base/repository.config
    |-- was-nd-fp-9.0.5.28/repository.config
    `-- java8/repository.config
```

The repository set must expose `com.ibm.websphere.ND.v90` and
`com.ibm.java.jdk.v8`. The installation module asks Installation Manager to
install from that complete set and then requires `versionInfo.sh` to report the
exact configured version. It refuses Base-only installations, implicit
downgrades, and mismatched maintenance levels.

### Configure lifecycle variables

Typical group variables are:

```yaml
---
was_media_root: /was855
was_version: 9.0.5.28
was_install_root: /opt/WebSphere/AppServers
was_im_install_root: /opt/IBM/InstallationManager
was_im_shared_root: /opt/IBM/IMShared
was_os_user: was
was_os_group: was

was_dmgr_profile_name: Dmgr01
was_dmgr_node_name: DmgrNode01
was_cell_name: LabCell01
was_dmgr_soap_port: 8879

was_clusters:
  - name: AppCluster01
    prefer_local: true
    members:
      - node: Node01
        name: server1
        weight: 2
      - node: Node02
        name: server1
        weight: 2
```

### Apply roles in order

```yaml
---
- name: Install WebSphere ND everywhere
  hosts: was_hosts
  gather_facts: true
  roles:
    - role: waslab.wasnd.install

- name: Create and start the deployment manager
  hosts: was_dmgr
  gather_facts: true
  roles:
    - role: waslab.wasnd.deployment_manager

- name: Create and federate managed profiles
  hosts: was_nodes
  gather_facts: true
  serial: 1
  roles:
    - role: waslab.wasnd.managed_node

- name: Declare clusters and members
  hosts: was_dmgr
  gather_facts: false
  become: true
  become_user: was
  roles:
    - role: waslab.wasnd.cell
```

Run it with the supplied inventory and Vault file:

```bash
ansible-playbook \
  -i inventory/production.yml \
  playbooks/converge-was.yml \
  --ask-vault-pass
```

The repository contains the equivalent example at
`ansible/playbooks/was_converge_cell.yml`.

### Optional systemd units

The deployment-manager and managed-node roles default
`was_systemd_enabled: false`. On an actual systemd host, setting it to `true`
creates and enables a Dmgr or node-agent unit. This also persists an
IBM-encoded SOAP credential in the profile so its stop script can run
unattended.

Review the service names and credential-storage policy before enabling it:

```yaml
was_systemd_enabled: true
was_systemd_service_name: was-dmgr
was_node_systemd_service_name: was-nodeagent-appsrv01
```

## Role reference

| Role | Run on | Purpose | Important variables |
|---|---|---|---|
| `waslab.wasnd.install` | Every WAS host | OS prerequisites, service account, Installation Manager, ND and Java | `was_media_root`, `was_version`, `was_install_root`, `was_manage_os_packages` |
| `waslab.wasnd.deployment_manager` | Dmgr host | Create/start secured Dmgr profile; optional systemd | `was_dmgr_profile_name`, `was_dmgr_node_name`, `was_cell_name`, credentials |
| `waslab.wasnd.managed_node` | Each application host | Create managed profile, federate it, start node agent | `was_node_profile_name`, `was_node_name`, `was_dmgr_host`, credentials |
| `waslab.wasnd.cell` | Dmgr host | Create declared clusters/members and synchronize changed nodes | `was_clusters`, `was_sync_after_cell_change` |
| `waslab.wasnd.rolling_restart` | Dmgr host | Restart members sequentially with optional HTTP health gate | `was_cluster_members`, `was_rolling_health_url`, retry settings |
| `waslab.wasnd.wave_reboot` | Each planned managed-node host | Stop, reboot, and restore discovered members and pre-maintenance application runtimes; recover a co-located Dmgr first | Variables generated by `was_wave_reboot.yml`, optional HTTP URLs, authorization/timeouts |
| `waslab.wasnd.collect_logs` | Any WAS host | Archive and fetch profile logs | `was_profile_name`, `was_log_destination`, `was_log_archive_path` |

The install role manages packages by default and recursively assigns the WAS
installation to `was:was`. Set `was_manage_os_packages: false` or call the
`installation` module directly when another team owns operating-system package
or filesystem permissions.

## Module reference

| Module | Primary target | Purpose | Check mode | Guarded removal |
|---|---|---|---:|---:|
| `installation` | Every WAS host | Install/update exact ND level through IBM Installation Manager | Yes | Yes |
| `profile` | Profile host | Create, back up, and delete Dmgr/managed/app-server profiles | Yes | Yes |
| `federation` | Managed-node host | Add or remove a profile from the Dmgr cell | Yes | Yes |
| `soap_credentials` | Profile host | Persist or restore IBM-encoded SOAP properties | Yes | No |
| `cell_info` | Dmgr or Base host | Return structured product and topology state | Yes | N/A |
| `topology_info` | Managed-node host | Discover local profiles, identities, owners, cell/node names, and Dmgr SOAP port | Yes | N/A |
| `wave_plan` | Controller | Correlate host profile facts with live Dmgr state and calculate safe Node 2/Node 1 waves | Yes | N/A |
| `cluster` | Dmgr host | Create/start/stop/delete a cluster | Yes | Yes |
| `cluster_member` | Dmgr host | Create/start/stop/restart/delete a member | Yes | Yes |
| `application` | Dmgr or Base host | Checksum-install/update/start/stop/delete WAR/EAR content | Yes | Yes |
| `application_info` | Dmgr or Base host | Discover a live app's modules, runtime instances, target mappings, context roots, and virtual hosts | Yes | N/A |
| `application_export` | Dmgr or Base host | Export a complete installed EAR for guarded rollback | Yes | N/A |
| `log_delta` | Any WAS host | Mark logs and return only bounded deployment-time additions | Yes | N/A |
| `jvm_heap` | Dmgr host | Set heap values for all members in a cluster | Yes | N/A |
| `node_sync` | Dmgr host | Invoke NodeSync MBeans | Yes | N/A |
| `wsadmin` | Dmgr or Base host | Run caller-supplied Jython | No | Script-defined |
| `release_artifact` | Any managed host | Validate an immutable EAR/WAR path, SHA-256, size, and ZIP structure | Yes | N/A |
| `release_lock` | Any managed host | Atomically serialize releases per application | Yes | Explicit release |
| `release_record` | Any managed host | Persist the current and prior known-good immutable release | Yes | N/A |
| `smtp_report` | Controller or managed host | Send plain/HTML status reports and attachments through SMTP | Yes | N/A |
| `aap_template_setup` | AAP execution environment | Reconcile this Project's operational templates, credential-launch policy, forks, and surveys through the controller API | Yes | N/A |

Use `ansible-doc waslab.wasnd.<module>` for every option and return value.

## Check mode and idempotency

Run a dry check before a change window:

```bash
ansible-playbook playbooks/change.yml --check --diff
```

All first-class modules support check mode. The `wsadmin` escape-hatch module
does not. Configuration modules compare current WebSphere objects before
changing them. Application updates additionally use the protected remote
checksum ledger. Runtime requests such as `state: restarted` are inherently
changes.

Most modules return `before` and `after` dictionaries. Register those results
for change records or AWX artifacts:

```yaml
- name: Start cluster
  waslab.wasnd.cluster:
    name: AppCluster01
    state: started
  register: cluster_operation

- ansible.builtin.debug:
    var: cluster_operation.after
```

## Destructive-operation safeguards

The following removals require both `state: absent` and
`allow_destructive: true`:

- WebSphere installation
- profile
- federation
- cluster
- cluster member
- application

For example:

```yaml
- name: Deliberately uninstall an application
  waslab.wasnd.application:
    name: payroll
    state: absent
    allow_destructive: true
```

Use a teardown order that respects WebSphere dependencies: applications,
members, clusters, federation, profiles, then product installation. Profile
removal stops and backs up the profile before `manageprofiles.sh -delete`.
Product uninstallation refuses to proceed while registered profiles remain and
does not uninstall IBM Installation Manager itself.

## AWX usage

For AWX or Ansible Automation Platform:

1. Make the collection available in the project at
   `collections/ansible_collections/waslab/wasnd`, or bake the built artifact
   into the execution-environment image.
2. Ensure the project `ansible.cfg` includes that collection path.
3. Add a Machine credential for SSH and privilege escalation.
4. Add a protected credential that injects `was_admin_user` and
   `was_admin_password`.
5. Target Dmgr-only administrative jobs at `was_dmgr`; target installation,
   profile, or log jobs at the appropriate host groups.
6. Enable job slicing or parallelism only for tasks that are safe to execute
   concurrently. Federate new nodes serially.

When this repository itself is the AAP Project, create one manual setup job
template whose playbook is the root `setup.yml`. Attach only the AAP controller
credential, then launch it to create or update the repository-managed
operational template and survey. The setup job contributes its Project,
Inventory, and Execution Environment. The generated job prompts natively for
the Machine and protected WebSphere credentials at each launch. See the
repository-level
[`AAP_SELF_SETUP.md`](../../../../../../docs/AAP_SELF_SETUP.md) runbook for the
exact settings.

The lab's `WAS - Update Existing Application` template is the small operator
surface: application name, immutable version, change ticket, and optional
preflight. It validates the name against live WAS, preserves the installed
targets and bindings, exports a rollback EAR, updates, starts, health-checks,
and prints the deployment-only SystemOut/SystemErr delta plus a structured AWX
artifact. It intentionally refuses new applications, because a new install's
targets and bindings cannot be inferred safely.

Use the repository's
[`existing-application release pipeline`](existing-application-pipeline.md)
as the operator and CI runbook. It defines the immutable release contract,
four-field launch, numbered stages, report/status meanings, rollback procedure,
and production controls.

For an ND inventory, point the same job at the Dmgr group and keep these as
template/inventory variables rather than survey questions:

```yaml
deployment_target_group: was_dmgr
was_deployment_profile_type: dmgr
was_deployment_sync_nodes:
  - Node01
  - Node02
was_deployment_log_paths:
  - /opt/WebSphere/AppServers/profiles/Dmgr01/logs/dmgr/SystemOut.log
  - /opt/WebSphere/AppServers/profiles/Dmgr01/logs/dmgr/SystemErr.log
```

The health URL in each immutable manifest should then be the load-balanced or
otherwise authoritative application endpoint. The operator survey remains the
same four fields.

The other Base job templates demonstrate the genuine wsadmin probe, sample
deployment, and HTTP health check. The ND job templates demonstrate status, cluster start/stop, node
synchronization, rolling restart, application deployment, heap configuration,
log collection, and HTTP health checks. `WAS - Deploy Clustered EAR` adds a
survey-driven validation, native approval, deployment, rollback, and email
workflow. See the [clustered EAR/WAR release guide](clustered-ear-releases.md)
for the application catalog, immutable manifest, survey fields, SMTP setup,
cluster semantics, statuses, and recovery procedure.

## Troubleshooting

### `wsadmin.sh is missing or not executable`

Verify `install_root`, `profile_name`, and the host targeted by the play. Cell
operations normally run on the Dmgr operating-system host with profile
`Dmgr01`.

### SOAP connection failures

Confirm the Dmgr is running, its SOAP connector is listening, and `host` and
`port` are correct from the managed host. The default is `localhost:8879`
because wsadmin normally runs on the Dmgr host.

On the supplied Base image, first boot can generate a localhost SSL signer that
is not yet in the profile client trust store. The lab entrypoint accepts only
that same-container localhost signer before declaring the service healthy. On
other environments, validate and import the expected server signer according
to your organization's certificate process; do not blindly auto-accept a
remote signer.

### Permission errors under the profile

Run WebSphere operations with `become: true` and `become_user: was`, or grant
the connecting account the permissions required by your organization's WAS
service-account policy.

### Federation cannot reach the Dmgr

The `managed_node` role runs `addNode.sh` on the application host. Its
`was_dmgr_host` must resolve and its `was_dmgr_soap_port` must be reachable from
that host.

### Requested node is unavailable during synchronization

Start the node agent and confirm its node name matches the cell configuration.
`node_sync` reports requested nodes without a live NodeSync MBean in its
`unavailable` return list.

### Application archive does not exist

`application.src` is a managed-host path. Use `ansible.builtin.copy` first, or
stage the archive through your deployment pipeline.

### Installed version differs from the requested version

Make sure the repositories mounted below `media_root` resolve to the desired
fix pack. The module deliberately fails rather than accepting an unexpected
edition or maintenance level.

## Validate changes to the collection

From the lab repository root:

```powershell
.\lab.ps1 collection-test
.\lab.ps1 collection-build
```

With licensed media and the genuine lab topology running:

```powershell
.\lab.ps1 collection-integration
```

The integration suite executes the collection against real ND `wsadmin.sh` and
repeats idempotent operations. It is intentionally blocked when authorized IBM
media is absent.

The official Base ILAN integration is available without ND media:

```powershell
.\lab.ps1 was-base-up
.\lab.ps1 collection-base-integration
```

It requires Base 9.0.5.28, executes both `cell_info` and a caller-supplied
Jython file through genuine profile `wsadmin.sh`, installs/starts a WAR, proves
application idempotency, and checks the live endpoint.
