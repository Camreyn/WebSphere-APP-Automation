# Operations

## First-time control-plane setup

Run these commands in PowerShell from the repository root:

```powershell
.\lab.ps1 init
.\lab.ps1 preflight
.\lab.ps1 awx-up
.\lab.ps1 bootstrap-awx
```

This starts the one-page portal and read-only Git service, creates the Kind AWX
control plane, and idempotently provisions the organization, inventory, four
hosts, protected credentials, project, execution environment, fifteen job
templates, and the approval-gated clustered application workflow. AWX and Git
do not require IBM media.

## Genuine WebSphere Base ILAN runtime

The fastest genuine `wsadmin.sh` path does not require Passport Advantage
media:

```powershell
.\lab.ps1 was-base-up
.\lab.ps1 collection-base-integration
.\lab.ps1 bootstrap-awx
.\lab.ps1 awx-base-integration
```

The first command builds a thin SSH/Ansible layer over IBM's pinned official
traditional WebSphere Base 9.0.5.28 ILAN image. It persists `AppSrv01`, applies
the generated lab password, trusts only its own first-boot localhost SSL
signer, and starts `server1`. The integration command proves product identity,
executes a custom Jython script through the collection, installs and starts a
WAR, verifies a no-change second pass, and checks HTTP 200.
The final command launches the three Base job templates through AWX and waits
for each controller job to finish successfully.

## Trusted-LAN access

The application containers retain desktop-only `127.0.0.1` bindings. Publish
the approved lab ports on the desktop's current IPv4 address through the
project's TCP gateway with:

```powershell
.\lab.ps1 lan-up
.\lab.ps1 lan-status
.\lab.ps1 urls
```

No Windows elevation or `netsh portproxy` is used. The command starts a
reversible HAProxy TCP gateway that binds the selected desktop address and
forwards AWX, the portal, Git, WAS web/SOAP ports, HAProxy, direct member ports,
and the four SSH ports over the isolated Docker network. It does not expose the
raw Kind Kubernetes API. Any client that can route to the desktop can connect,
so use this only on the trusted network described for this lab.

If DHCP changes the desktop address, run `lan-up` again; Compose recreates the
gateway on the new address. Remove only the gateway owned by this project with:

```powershell
.\lab.ps1 lan-down
```

## Genuine WebSphere ND runtime

Place authorized Installation Manager and repository content as described in
`artifacts/ibm/README.md`, then run:

```powershell
.\lab.ps1 was-build
.\lab.ps1 was-up
.\lab.ps1 bootstrap-awx
.\lab.ps1 verify
```

The first runtime start creates `Dmgr01`, two independent `AppSrv01` profiles,
federates `Node01` and `Node02`, and creates `AppCluster01` with one `server1`
member per node. Named Docker volumes preserve profile state. The expected
maintenance level is validated as WebSphere ND 9.0.5.28.

## Credentials

- AWX username: `admin`
- AWX password: `.secrets/awx_admin_password`
- WebSphere username: `wsadmin`
- WebSphere password: `.secrets/was_admin_password`
- SSH private key: `.secrets/ansible_lab`

Generated values are ignored by Git. Ansible parameters containing passwords
use `no_log`; the collection creates a private temporary SOAP properties file,
runs IBM's `PropFilePasswordEncoder.sh`, invokes the profile's real
`bin/wsadmin.sh`, then removes the temporary copy. The optional systemd roles
persist only an encoded SOAP properties file.

## Collection workflow

The source lives at
`ansible/collections/ansible_collections/waslab/wasnd`. The repository's
`ansible.cfg` makes it available to AWX and local syntax checks without an
online Galaxy dependency.

```powershell
.\lab.ps1 collection-test         # ansible-test sanity + all syntax checks
.\lab.ps1 collection-build        # creates ansible/dist/waslab-wasnd-*.tar.gz
.\lab.ps1 collection-base-integration # real Base wsadmin + WAR tests; runnable now
.\lab.ps1 collection-integration  # real wsadmin idempotency tests; media gated
```

For standalone RHEL-style hosts, mount entitled media at `/was855` or override
`was_media_root`, install the built artifact with `ansible-galaxy collection
install`, and use `ansible/playbooks/was_converge_cell.yml` as the topology
example. Removal of an installation, profile, member, application, or
federation is guarded by `allow_destructive: true`.

See the collection's
[`docs/usage.md`](../ansible/collections/ansible_collections/waslab/wasnd/docs/usage.md)
for complete installation, inventory, role, module, AWX, and troubleshooting
instructions.

For the developer-share-to-production process, survey, SMTP credential,
approval, rollback, and error-reporting details, see the
[`clustered EAR/WAR release guide`](../ansible/collections/ansible_collections/waslab/wasnd/docs/clustered-ear-releases.md).

## AWX job templates

The templates cover Base status/wsadmin, Base sample deployment and health,
plus ND status, start, stop, node synchronization, rolling member restart,
parallel Node 2 then Node 1 operating-system reboot waves, sample deployment,
JVM heap changes, log collection, HTTP health
checks, and three clustered-release phases. The `WAS - Deploy Clustered EAR`
workflow connects validation to an operator approval and then deployment or a
nondeployment report. Administrative jobs target `was-dmgr` and use fully qualified
`waslab.wasnd` modules. Those modules execute:

```text
/opt/WebSphere/AppServers/profiles/Dmgr01/bin/wsadmin.sh
```

The scripts use IBM `AdminConfig`, `AdminControl`, `AdminTask`, and `AdminApp`
objects through Jython. They do not simulate a WAS API.

`WAS - Reboot Nodes by Wave` is guarded by
`was_maintenance_allow_reboot: true`. Each inventory host must declare wave 1
or 2 plus direct application health URLs. Node 2 is wave 1, so each Node 1 Dmgr
remains available while its partner reboots. Node 1 is wave 2 and sets
`was_maintenance_hosts_dmgr: true`; the role stops Dmgr last, starts it first,
and waits for SOAP before recovering WebSphere. Wave 2 is blocked unless every
wave-1 host stopped, rebooted, restarted, and passed health checks. The Docker
lab records the wave metadata for illustration but intentionally has no direct
reboot-health configuration, because its containers are not production
operating-system reboot targets.

The local bootstrap and GitHub Actions bootstrap both read the shared template
and survey definition from `config/aap/wave_reboot.yml`. See
[`GITHUB_AAP_SETUP.md`](GITHUB_AAP_SETUP.md) for the repository environment,
token, inventory, credential, project, and runner settings.

## Daily commands

```powershell
.\lab.ps1 status
.\lab.ps1 urls
.\lab.ps1 verify
.\lab.ps1 down
.\lab.ps1 awx-up
.\lab.ps1 was-base-up
.\lab.ps1 was-up
```

`down` stops containers but preserves data. `destroy -Force` deletes the Kind
cluster and all four WebSphere profile volumes. Generated secrets and IBM
media remain unless removed separately.

## Troubleshooting

- Run `.\lab.ps1 status` first, then `.\lab.ps1 lan-status` for remote access.
- Inspect AWX with `.tools\kubectl.exe --kubeconfig .data\kubeconfig -n awx get pods`.
- Inspect the operator with `.tools\kubectl.exe --kubeconfig .data\kubeconfig -n awx logs deployment/awx-operator-controller-manager`.
- Inspect cell creation with `docker --context desktop-linux exec wasnd-lab-dmgr tail -100 /opt/WebSphere/AppServers/profiles/Dmgr01/logs/lab-cell-bootstrap.log`.
- Re-run `.\lab.ps1 bootstrap-awx` after collection or playbook changes; it republishes and synchronizes the Git project.
