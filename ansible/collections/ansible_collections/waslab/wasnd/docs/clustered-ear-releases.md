# Clustered EAR and WAR release workflow

This workflow replaces the usual sequence of opening the WebSphere admin
console, locating an archive on a share, updating the application, saving,
synchronizing nodes, and checking each cluster member. It uses the genuine
deployment-manager `wsadmin.sh` through `waslab.wasnd.application`.

The supplied AWX workflow is named `WAS - Deploy Clustered EAR`. One launch
updates the application once at cell scope through the Dmgr. WebSphere then
targets the complete cluster; Ansible does not deploy the EAR independently to
Node 1 and Node 2.

## Release flow

1. A build pipeline writes an EAR or WAR into a new, versioned directory on
   the release share and writes `release.yml` beside it.
2. An operator launches the AWX workflow and completes its survey.
3. The validation job checks the request, manifest, SHA-256, ZIP structure,
   archive size, path boundary, application catalog, cluster topology, member
   runtime state, deployment lock, previous release record, and current HTTP
   health.
4. AWX pauses at a native approval node for up to 24 hours.
5. After approval, the deployment job repeats the entire preflight. This
   prevents an archive from being substituted while approval is pending.
6. The job acquires a per-application atomic lock, stages the validated file,
   performs one application update through the Dmgr, synchronizes every node
   represented in the target cluster, starts the application, and checks both
   load-balanced and direct-member URLs.
7. A successful release becomes the rollback baseline. A failed update or
   health check automatically restores the prior validated immutable archive
   when one is available.
8. Validation, rejection, success, no-change, and failure paths persist a
   verbose report and optionally email it to the requested team recipients.

## Immutable release share

Give the Dmgr operating-system host read-only access to the developer release
share. A release has this shape:

```text
/mnt/was-releases/
`-- payroll/
    `-- 2026.08.08-1/
        |-- payroll.ear
        `-- release.yml
```

Use a new directory for every release. Never overwrite an approved version.
The manifest format is:

```yaml
schema_version: 1
application: payroll
version: 2026.08.08-1
filename: payroll.ear
sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
source_commit: 45d91a73
built_at: "2026-08-08T21:10:00Z"
built_by: build-pipeline
release_notes: Fixes the invoice reconciliation defect.
```

The first five fields are enforced. The remaining provenance fields are
included in reports. The archive validator also rejects corrupt ZIP content,
unsafe member paths, wrong extensions, files outside the approved application
root, and archives larger than the catalog limit.

For a production SMB share, mount it on the Dmgr host with a dedicated
read-only service identity. For NFS, use a read-only mount and restrict the
export to the Dmgr host. The execution account needs read access only. Do not
give AWX or WebSphere permission to modify the release directories.

## Configure the application catalog

Edit `ansible/vars/was_application_catalog.yml`. Operators select only the
catalog key; cluster names, application names, paths, health checks, and policy
remain source-controlled.

```yaml
was_application_catalog:
  payroll:
    display_name: Payroll
    enabled: true
    was_name: PayrollApplication
    cluster: PayrollCluster
    context_root: /payroll
    artifact_root: /mnt/was-releases/payroll
    artifact_filename: payroll.ear
    archive_type: ear
    manifest_filename: release.yml
    maximum_size_mb: 1024
    allow_initial_install: false
    require_all_members_running: true
    preflight_health_required: true
    health_urls:
      - https://payroll.example.test/health
      - http://appnode01.example.test:9080/payroll/health
      - http://appnode02.example.test:9080/payroll/health
    health_expected_status: 200
    health_expected_text: UP
    health_validate_certs: true
    health_retries: 30
    health_delay: 10
```

Duplicate the entry for each application, then rerun:

```powershell
.\lab.ps1 bootstrap-awx
```

The bootstrap republishes the Ansible project, synchronizes it in AWX, and
rebuilds the survey's Application choices from enabled catalog entries.

## Generate the local lab release

The repository release directory is mounted read-only into the Dmgr container
at `/mnt/was-releases`.

```powershell
.\lab.ps1 sample-release -ReleaseVersion lab-1
```

The command prints the exact SHA-256 to paste into the survey. It creates:

```text
artifacts/releases/was-lab/lab-1/was-lab.war
artifacts/releases/was-lab/lab-1/release.yml
```

Choose a new version for the next release. `-Force` exists only to make local
lab iteration convenient; an actual release pipeline should reject overwrite
attempts.

## Configure team email

Copy the ignored example and supply the team's SMTP relay settings:

```powershell
Copy-Item config\smtp.example.yml .secrets\smtp.yml
notepad .secrets\smtp.yml
.\lab.ps1 bootstrap-awx
```

Example:

```yaml
name: WAS Team SMTP
host: smtp.example.com
port: 587
username: was-automation@example.com
password: replace-with-the-relay-secret
from_address: was-automation@example.com
starttls: true
ssl: false
default_to:
  - middleware-operations@example.com
  - application-support@example.com
```

The bootstrap creates a custom `WebSphere SMTP Relay Credential`, stores the
password as an encrypted AWX secret, and attaches the credential to all three
release phase templates. It uses `default_to` only to prefill the survey; an
operator can change the recipients for a particular request.

Use either STARTTLS (commonly port 587), implicit TLS (commonly port 465), or
neither when an internal relay explicitly requires plain SMTP. Do not enable
both `starttls` and `ssl`. If authentication is not required, leave username
and password empty.

Email is best-effort. An SMTP problem is printed in the AWX job without
replacing or concealing the actual deployment result. The complete report and
a structured attempted/delivered/error summary are saved in the AWX job
artifacts. SMTP passwords are protected with `no_log` and are never included in
the error report.

## Launch the AWX survey

Open Templates in AWX, select `WAS - Deploy Clustered EAR`, and click Launch.
The survey contains:

| Field | Meaning |
|---|---|
| Application | Enabled source-controlled catalog key |
| Immutable release version | Directory below that application's share root |
| Approved EAR/WAR SHA-256 | Must match the survey, manifest, and actual bytes |
| Change or request number | Audit identifier and part of lock ownership |
| Requested by | Developer or release owner |
| Team email recipients | Comma- or semicolon-separated addresses |
| Deployment strategy | `maintenance` or `in_place` |
| Automatically roll back | Restore the last successfully recorded release |
| Force deployment | Reapply content even if the checksum is current |
| Send status email | Enable or disable SMTP reporting for this run |
| Release notes | Free-form context included in the report |

After validation succeeds, open the workflow job, inspect the validation job's
artifact and checksum, then approve or deny the approval node. Denial or expiry
does not touch WebSphere and produces a `NOT_DEPLOYED` report.

## Strategy choice and cluster behavior

`maintenance` is the safe default. It stops the application, updates the full
archive, synchronizes nodes, starts it, and runs health checks. Expect an
application outage during the update.

`in_place` leaves the application running while WebSphere updates it. This can
reduce interruption, but it is not a guarantee of zero downtime. Class-loader
changes, shared sessions, database migrations, plug-in routing, and application
startup behavior can still produce errors. Validate this mode per application
in non-production.

For genuine rolling or blue/green application deployment, use two separately
addressable clusters or a tested application-specific rollout design. Merely
installing an EAR once to a two-member cluster does not provide an atomic,
zero-downtime rolling update.

## Statuses and error detail

Reports use these principal statuses:

| Status | Meaning |
|---|---|
| `VALIDATED` | Preflight passed and the workflow is ready for approval |
| `VALIDATION_FAILED` | No deployment occurred; preflight rejected the request |
| `NOT_DEPLOYED` | Approval was denied or expired |
| `SUCCESS` | Content changed and post-deployment checks passed |
| `NO_CHANGE` | The recorded checksum was already current |
| `FAILED` | Deployment failed and automatic rollback was disabled |
| `FAILED_NO_ROLLBACK` | Deployment failed before any previous baseline existed |
| `FAILED_ROLLED_BACK` | Deployment failed and the prior release was restored |
| `FAILED_ROLLBACK_FAILED` | Both deployment and rollback failed; intervene immediately |

The report includes the request and AWX IDs, expected and actual checksum,
archive metadata, manifest provenance, the complete cell snapshot, application
operation result, synchronization result, every endpoint result, rollback
record and outcome, and the failed task's message, return code, stdout, stderr,
and exception text when Ansible supplies them.

The first successful managed release establishes the initial rollback
baseline. Until then, an update failure correctly reports
`FAILED_NO_ROLLBACK`; it cannot invent a known-good archive.

## Concurrency and recovery

The AWX deployment phase is globally serialized because concurrent `AdminApp`
updates can both save the same Dmgr cell configuration. Validation, approval,
and rejection reporting can still overlap. The deployment playbook additionally
acquires an atomic directory lock per WebSphere application, which protects the
same application when the playbook is invoked outside that AWX template. Locks
include the AWX job ID, ticket, requester, version, and timestamp. They are
released in the playbook's cleanup path. Each application's checksum and
rollback ledgers also live in a separate state subdirectory.

If a controller or host crash leaves a lock behind, inspect it before removing
it:

```yaml
- waslab.wasnd.release_lock:
    name: PayrollApplication
    state: status
    lock_root: /var/tmp/waslab-locks
```

Only break a stale lock after confirming that its job and WebSphere operation
are no longer running:

```yaml
- waslab.wasnd.release_lock:
    name: PayrollApplication
    state: acquired
    owner: recovery-CHG123456
    lock_root: /var/tmp/waslab-locks
    stale_after: 14400
    break_stale: true
```

## Production adoption checklist

- Test the exact collection and playbooks against a non-production WAS ND 9
  cell and its genuine `wsadmin.sh`.
- Back up WebSphere configuration independently of application rollback.
- Make application release directories immutable and the share read-only to
  the Dmgr account.
- Put WAS and SMTP secrets in AAP/AWX credentials or an approved secret
  backend, never source control.
- Replace lab IP health URLs with production load-balancer and direct-member
  endpoints.
- Confirm the Dmgr profile owner can write the state ledger directory.
- Decide whether the first automated release is only a baseline capture or a
  controlled update with an independently prepared rollback archive.
- Integrate ticket validation and separation-of-duties approval if required by
  organizational policy.
