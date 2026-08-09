#!/usr/bin/env bash
set -Eeuo pipefail

password_file=/run/secrets/was_admin_password
authorized_key_file=/run/secrets/ansible_authorized_key

if [[ ! -s ${password_file} ]]; then
  echo "BOOTSTRAP_ERROR: missing ${password_file}. Run lab.ps1 init." >&2
  exit 40
fi
if [[ ! -s ${authorized_key_file} ]]; then
  echo "BOOTSTRAP_ERROR: missing ${authorized_key_file}. Run lab.ps1 init." >&2
  exit 41
fi

# IBM's startup script consumes /tmp/PASSWORD and securely updates the local
# WebSphere file registry before starting server1.  Copying from a Compose
# secret keeps the credential stable across container recreation.
install -m 0600 -o was -g root "${password_file}" /tmp/PASSWORD
install -d -m 0700 -o ansible -g ansible /home/ansible/.ssh
install -m 0600 -o ansible -g ansible "${authorized_key_file}" /home/ansible/.ssh/authorized_keys

ssh-keygen -A >/dev/null
/usr/sbin/sshd -t
/usr/sbin/sshd

profile_root=/opt/IBM/WebSphere/AppServer/profiles/${PROFILE_NAME:-AppSrv01}
soap_port=${WAS_BASE_SOAP_PORT:-8880}
signer_ready=${profile_root}/.waslab-local-signer-ready
rm -f "${signer_ready}"

trust_local_signer() {
  local first_probe second_probe
  first_probe=$(mktemp)
  second_probe=$(mktemp)
  trap 'rm -f "${first_probe}" "${second_probe}"' RETURN

  for _ in $(seq 1 90); do
    if timeout 1 bash -c "</dev/tcp/127.0.0.1/${soap_port}" 2>/dev/null; then
      break
    fi
    sleep 2
  done
  if ! timeout 1 bash -c "</dev/tcp/127.0.0.1/${soap_port}" 2>/dev/null; then
    echo "BOOTSTRAP_ERROR: local SOAP connector ${soap_port} did not become ready." >&2
    return 42
  fi

  # A new traditional-WAS profile prompts before trusting its generated SSL
  # signer.  Trust only this container's localhost endpoint; credentials are
  # deliberately omitted, so no password appears in a process argument.
  timeout 45 /usr/sbin/runuser -u was -- \
    "${profile_root}/bin/wsadmin.sh" -lang jython -conntype SOAP \
    -host localhost -port "${soap_port}" -c 'print "WASLAB_SIGNER_PROBE"' \
    </dev/null >"${first_probe}" 2>&1 || true
  if grep -q "SSL SIGNER EXCHANGE PROMPT" "${first_probe}"; then
    printf 'y\n' | timeout 45 /usr/sbin/runuser -u was -- \
      "${profile_root}/bin/wsadmin.sh" -lang jython -conntype SOAP \
      -host localhost -port "${soap_port}" -c 'print "WASLAB_SIGNER_ACCEPTED"' \
      >/dev/null 2>&1 || true
  fi

  timeout 45 /usr/sbin/runuser -u was -- \
    "${profile_root}/bin/wsadmin.sh" -lang jython -conntype SOAP \
    -host localhost -port "${soap_port}" -c 'print "WASLAB_SIGNER_VERIFY"' \
    </dev/null >"${second_probe}" 2>&1 || true
  if grep -q "SSL SIGNER EXCHANGE PROMPT" "${second_probe}"; then
    echo "BOOTSTRAP_ERROR: unable to trust the local WebSphere SSL signer." >&2
    return 43
  fi
  install -m 0600 -o was -g root /dev/null "${signer_ready}"
}

trust_local_signer &

if [[ $# -eq 0 ]]; then
  set -- env JVM_EXTRA_CMD_ARGS=-Xnoloa /work/start_server.sh
fi

# Preserve IBM's original command and run it as the image's native `was` user.
exec /usr/sbin/runuser -u was -- "$@"
