# Local WebSphere ND 9 + AWX lab

This project recreates the operational shape of a traditional WebSphere
Application Server Network Deployment environment on one Docker Desktop host:

- one immediately runnable, genuine IBM WebSphere traditional Base 9.0.5.28
  ILAN server for real `AppSrv01/bin/wsadmin.sh` and application testing,
- one deployment manager profile (`Dmgr01`),
- two separately federated application-node profiles (`AppSrv01`),
- a two-member `AppCluster01`,
- AWX 24.6.1 with operational templates and an approval-gated release workflow,
- a four-field `WAS - Update Existing Application` job with live discovery,
  automatic export/rollback, health validation, and deployment-only WAS logs,
- the buildable `waslab.wasnd` Ansible collection,
- a sample application behind HAProxy, and
- a one-stop portal whose links follow the desktop IP used to open it.

The runnable Base target derives from IBM's official public ILAN image; this
repository does not redistribute its layers. WebSphere ND still requires
authorized IBM WAS ND 9 media. The project does not emulate WebSphere and does
not use Liberty.

## Quick start

Run PowerShell from this directory:

```powershell
.\lab.ps1 init
.\lab.ps1 preflight
.\lab.ps1 awx-up
.\lab.ps1 was-base-up
.\lab.ps1 collection-base-integration
.\lab.ps1 awx-base-integration
.\lab.ps1 sample-release -ReleaseVersion lab-1
.\lab.ps1 bootstrap-awx
.\lab.ps1 lan-up
```

`lan-up` starts a project-owned Docker TCP gateway bound only to the selected
desktop IPv4 address and records its state in `.data/lan-access.json`; it does
not need Windows administrator approval or `netsh portproxy`. From another
device, run `.\lab.ps1 urls` and open the printed desktop-IP portal URL. Remove
the gateway and all its LAN listeners with:

```powershell
.\lab.ps1 lan-down
```

The Kubernetes API remains desktop-only. AWX HTTP, Git protocol, and the lab's
HTTP endpoints are intentionally unencrypted and should be used only on a
trusted network.

## Genuine wsadmin lab without ND media

Start IBM's official traditional WebSphere Base 9.0.5.28 ILAN image and run the
real collection integration:

```powershell
.\lab.ps1 was-base-up
.\lab.ps1 collection-base-integration
```

This verifies the Base product and version, invokes
`/opt/IBM/WebSphere/AppServer/profiles/AppSrv01/bin/wsadmin.sh` over SOAP 8880,
runs caller-supplied Jython, installs and starts a WAR, repeats the deployment
to prove idempotency, and requests the live application. Base is a stand-alone
server; it does not supply Dmgr, federation, NodeSync, or cluster behavior.
The sample WAR deliberately spends 10 seconds in its Servlet initialization
listener whenever WebSphere starts it, making application restarts and AWX
updates visible in the administrative console. Change
`waslab.startupDelaySeconds` in `sample-app/WEB-INF/web.xml` and rebuild with
`.\lab.ps1 init` to adjust or disable the delay.
After `.\lab.ps1 bootstrap-awx`, launch the AWX job template
`WAS Base - Restart Sample Application` to stop and start the application
through genuine `wsadmin.sh` while watching its status in the console.
Launch `WAS Base - Start Server and Discovered Applications` after a host or
container restart to ensure `server1` is running, discover the installed
applications live through `AdminApp.list()`, start every discovered application,
and write a consolidated report to the AWX job output and artifacts.

Three additional deterministic Java EE EAR examples are generated from
`config/test_ears.yml`. Build and deploy them locally with:

```powershell
.\.venv\Scripts\python.exe .\tools\build_test_ears.py
.\lab.ps1 bootstrap-awx
```

Then launch `WAS Base - Deploy Test EARs` in AWX. It installs `orders-test`,
`billing-test`, and `claims-test`, starts each application through genuine
`wsadmin.sh`, and verifies all three HTTP endpoints.

## Add genuine WebSphere ND

After placing entitled Installation Manager and WAS ND repositories below
`artifacts/ibm`, run:

```powershell
.\lab.ps1 was-build
.\lab.ps1 was-up
.\lab.ps1 bootstrap-awx
.\lab.ps1 verify
```

The resulting containers use the familiar paths
`/opt/WebSphere/AppServers/profiles/Dmgr01/bin/` and
`/opt/WebSphere/AppServers/profiles/AppSrv01/bin/`. AWX reaches the deployment
manager over SSH and the collection invokes the genuine Dmgr `wsadmin.sh` over
SOAP.

## Ansible collection

The embedded `waslab.wasnd` collection covers installation, profiles,
federation, SOAP credentials, clusters and members, applications, JVM heap,
node synchronization, cell inspection, and local Jython scripts. It also
contains install, deployment-manager, managed-node, cell, rolling-restart,
two-wave operating-system reboot, and log-collection roles. The wave reboot
runs every Node 2 application host concurrently before Node 1, keeping the
co-located Node 1 Dmgr available for the first wave. It discovers pairs,
profiles, cells, cluster members, applications, Dmgr placement, health state,
product family, WAS/Jython version, and waves from a host-only inventory. Its
built-in bridge supports the Jython 2.1 and 2.7 generations used by WAS 8.5.5
and WAS 9, including legacy BPM/BAW installations. It requires explicit reboot
authorization and restores every pre-maintenance WebSphere runtime; direct HTTP
checks remain optional. Destructive states require `allow_destructive: true`.

```powershell
.\lab.ps1 collection-test
.\lab.ps1 collection-build
# Runs now against IBM's official Base ILAN image:
.\lab.ps1 collection-base-integration
# Requires the genuine running WAS topology:
.\lab.ps1 collection-integration
```

The offline artifact is written to `ansible/dist/`. Collection defaults match
the work-style layout, including `/was855` as the licensed-media source on a
managed RHEL host and `/opt/WebSphere/AppServers` as the install root.

The [collection usage guide](ansible/collections/ansible_collections/waslab/wasnd/docs/usage.md)
contains copy-ready inventory, role, module, AWX, custom Jython, teardown, and
troubleshooting examples.

The [clustered EAR/WAR release guide](ansible/collections/ansible_collections/waslab/wasnd/docs/clustered-ear-releases.md)
covers the immutable share layout, application catalog, AWX survey and approval,
team email, cluster synchronization, health checks, locking, and automatic
rollback flow.

For routine updates to applications that already exist in WAS, operators can
launch `WAS - Update Existing Application` and enter only the exact application
name, release version, change ticket, and whether the run is preflight-only.
The job discovers existing WAS mappings instead of using an application catalog
and publishes its full report as both AWX output and a job artifact.

The [existing-application release pipeline](ansible/collections/ansible_collections/waslab/wasnd/docs/existing-application-pipeline.md)
is the operator and CI runbook for artifact publication, the four-field AWX
launch, numbered progress stages, logs, statuses, rollback, and production
controls.

The [in-AAP setup guide](docs/AAP_SELF_SETUP.md) describes the one manual
`setup.yml` job template. Launching it from the imported project idempotently
creates or updates the operational template, survey, and native credential and
fork prompts through AAP's own API; no GitHub runner is required.

See [operations](docs/OPERATIONS.md), [fidelity](docs/FIDELITY.md), and
[licensing](docs/LICENSING.md) for the operating and security boundaries.
