# Lifecycle guide

The collection manages traditional WebSphere Application Server Network
Deployment 9 and intentionally calls IBM's native tools. Defaults match this
lab but every path, profile, node, cell, cluster, port, and operating-system
user can be overridden.

## Provisioning sequence

1. Mount entitled Installation Manager and WAS repositories below `/was855`.
2. Apply `waslab.wasnd.install` to each RHEL-compatible host.
3. Apply `waslab.wasnd.deployment_manager` to the Dmgr host.
4. Apply `waslab.wasnd.managed_node` to each application host.
5. Apply `waslab.wasnd.cell` to declare clusters and members.

`ansible/playbooks/was_converge_cell.yml` demonstrates this sequence. The
install module discovers the agent installer and `repository.config` files,
runs `imcl`, and verifies both the ND edition and exact requested version with
`versionInfo.sh`. Profile creation uses `manageprofiles.sh`; federation uses
`addNode.sh`; administrative changes use the Dmgr profile's `wsadmin.sh` SOAP
client.

## Operational modules

- `cell_info`: return cell, node, server, cluster, and application state.
- `profile_runtime`: idempotently start, stop, or restart a deployment manager,
  node agent, or stand-alone application server with IBM's profile scripts.
- `cluster`: create, start, stop, or guardedly remove a cluster.
- `cluster_member`: create or guardedly remove an individual member.
- `application`: checksum-aware install/update/start/stop/guarded removal.
- `jvm_heap`: idempotently set initial and maximum JVM heap values.
- `node_sync`: synchronize one node or all federated nodes.
- `wsadmin`: transfer and run a caller-supplied Jython script through genuine
  `wsadmin.sh`.

The `rolling_restart` role processes members serially and the `collect_logs`
role gathers selected profile logs. Optional Dmgr and node-agent systemd units
are disabled by default because container lab hosts do not use systemd.

## Removal safety

Operations that remove registered WebSphere state require both `state: absent`
and `allow_destructive: true`. Profile removal stops the profile, creates a
backup, and invokes `manageprofiles.sh -delete`. Installation removal refuses
to proceed while registered profiles remain and never removes Installation
Manager itself.
