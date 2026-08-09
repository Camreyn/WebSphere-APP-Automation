# Security model

This collection is designed for a controlled administration network. Use
Ansible Vault, an automation-controller credential, or another secret backend
for `username` and `password`; do not commit them in inventory.

WebSphere SOAP passwords are never placed in the process argument list. A
module writes a mode-0600 temporary properties file, invokes IBM's
`PropFilePasswordEncoder.sh`, passes the encoded copy to the genuine profile
`wsadmin.sh`, and deletes it when the operation ends. Password-bearing module
arguments and command failures are redacted and marked `no_log`.

The `soap_credentials` module can deliberately persist an encoded properties
file when optional systemd units need unattended startup. Restrict that file to
the WebSphere operating-system account and rotate it whenever the administrative
credential changes.

The Docker lab's `lan-up` command publishes AWX HTTP, Git protocol, HTTP test
endpoints, SSH, and WAS administration ports to any routable client. Those
bindings are appropriate only on a trusted lab network. The command does not
publish the Kind Kubernetes API and `lan-down` removes the project-owned
Docker TCP gateway and all of its desktop-IP listeners.
