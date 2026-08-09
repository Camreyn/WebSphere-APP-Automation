# Immutable application releases

This directory is a local bind-mounted stand-in for a read-only workplace
release share. Generated releases are ignored by Git.

Create a sample release from the generated lab WAR:

```powershell
.\lab.ps1 sample-release -ReleaseVersion lab-1
```

The Dmgr container sees it at:

```text
/mnt/was-releases/was-lab/lab-1/was-lab.war
/mnt/was-releases/was-lab/lab-1/release.yml
```

The simple existing-application job uses the same layout without an app
catalog. Its manifest also requires a health check:

```yaml
schema_version: 1
application: orders
version: 2026.08.09.1
filename: orders.ear
sha256: <64 hexadecimal characters>
health:
  url: http://localhost:9080/orders/
  status_code: 200
  contains: Orders 2026.08.09.1
```

In AWX, launch `WAS - Update Existing Application`; enter application,
version, change ticket, and optionally choose preflight-only. WAS supplies the
existing deployment identity, modules, mappings, and bindings.

The end-to-end producer, operator, API, reporting, and recovery contract is in
[`existing-application-pipeline.md`](../../ansible/collections/ansible_collections/waslab/wasnd/docs/existing-application-pipeline.md).

For the local `orders-test` proof release only:

```powershell
.\.venv\Scripts\python.exe tools\build_test_release.py --version lab-2
```

`release.yml` binds the catalog application key, version, archive filename,
and SHA-256 to the submitted file. AWX compares all four values to its survey
and then validates the actual archive bytes and ZIP structure both before and
after approval.

At work, replace the application catalog's `artifact_root` with the read-only
SMB/NFS mount used on the Dmgr host. Do not overwrite a submitted version.

See the collection's
[`clustered-ear-releases.md`](../../ansible/collections/ansible_collections/waslab/wasnd/docs/clustered-ear-releases.md)
for the manifest schema and complete release process.
