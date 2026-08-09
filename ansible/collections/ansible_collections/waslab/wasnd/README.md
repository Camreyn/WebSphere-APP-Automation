# `waslab.wasnd`

`waslab.wasnd` automates traditional IBM WebSphere Application Server Network
Deployment 9 on RHEL-compatible systems. Its information, application, and
custom-Jython operations also work with traditional WebSphere Base. It uses IBM Installation Manager,
`manageprofiles.sh`, node federation commands, and the genuine profile
`wsadmin.sh`; it does not emulate WebSphere or contain IBM binaries.

The collection defaults match the accompanying lab:

- licensed media mounted below `/was855`,
- WebSphere at `/opt/WebSphere/AppServers`,
- `Dmgr01` and `AppSrv01` profiles,
- SOAP port `8879`, and
- operating-system account `was`.

All paths, names, ports, users, offering IDs, and topology lists are
configurable. Removal operations require `allow_destructive: true`.

The companion lab includes IBM's official Base ILAN 9.0.5.28 image as a
genuine, immediately runnable `wsadmin.sh` target. Cluster, member, node-sync,
federation, and Dmgr lifecycle operations still require Network Deployment.

## Example

```yaml
- name: Inspect the deployment manager cell
  hosts: was_dmgr
  become: true
  become_user: was
  module_defaults:
    group/waslab.wasnd.wasnd:
      install_root: /opt/WebSphere/AppServers
      profile_name: Dmgr01
      username: "{{ was_admin_user }}"
      password: "{{ was_admin_password }}"
  tasks:
    - name: Gather cell information
      waslab.wasnd.cell_info:
      register: was_cell

    - name: Ensure the application cluster is running
      waslab.wasnd.cluster:
        name: AppCluster01
        state: started
```

Start with the [complete usage guide](docs/usage.md). For production-style
application updates, use the [clustered EAR/WAR release guide](docs/clustered-ear-releases.md).
The companion [lifecycle](docs/lifecycle.md) and [security](docs/security.md)
notes provide shorter design-focused references.
