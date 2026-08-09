# Fidelity to the work environment

## Verified and runnable now

- IBM WebSphere Application Server traditional Base 9.0.5.28 from IBM's
  official ILAN container image; this is not Liberty or an emulator.
- A genuine application-server profile at
  `/opt/IBM/WebSphere/AppServer/profiles/AppSrv01`.
- Real `bin/wsadmin.sh`, Jython, `AdminConfig`, `AdminControl`, and `AdminApp`
  calls over the secured SOAP connector.
- A collection-driven WAR install, start, checksum-idempotency pass, and live
  HTTP request.
- AWX inventory and templates that can target the Base server over SSH.

## Faithful ND target after entitled media is supplied

- IBM WebSphere Application Server Network Deployment 9.0.5.28 binaries.
- Traditional profiles at `/opt/WebSphere/AppServers/profiles/Dmgr01` and
  `/opt/WebSphere/AppServers/profiles/AppSrv01`.
- One deployment manager, two federated nodes, and a two-member dynamic
  management topology represented as `AppCluster01`.
- The genuine profile `bin/wsadmin.sh` over its SOAP connector.
- Jython automation using IBM administrative objects.
- RHEL 9 userspace compatibility via Red Hat UBI 9 containers.
- Controller jobs, inventories, credentials, projects, and execution
  environments through AWX.

## Intentionally different

- WebSphere Base is a stand-alone server. It proves genuine administrative and
  application behavior but cannot validate Dmgr, federation, NodeSync, or
  cluster operations; those tests remain gated on real ND media.
- IBM's current Base ILAN image uses a UBI/RHEL 8 userspace. The separately
  built ND target uses UBI 9 to resemble the work hosts more closely.
- UBI 9 containers share Docker's Linux kernel; they are not full RHEL 9 VMs
  with systemd, SELinux policy, firewalld, Azure networking, or Azure disks.
- AWX 24.6.1 is the upstream project, not supported Ansible Automation Platform.
- HAProxy stands in for an enterprise ingress or IBM HTTP Server/plugin tier.
- TLS uses WebSphere's generated lab certificates. Host services bind to
  loopback and an explicitly enabled Docker TCP gateway publishes the selected
  ports on the desktop IPv4 address. It accepts any routable client; this is a
  trusted-LAN convenience, not a production security boundary.
- The raw Kind Kubernetes API remains bound to the desktop and is not included
  in the LAN forwarding set.
- Databases and profile volumes are single-host lab storage, not production HA.

The result is designed for realistic Ansible and `wsadmin` practice, not for
performance, security certification, or production deployment testing.
