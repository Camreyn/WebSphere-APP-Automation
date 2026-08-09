#!/usr/bin/env bash
set -Eeuo pipefail

was_root=${WAS_INSTALL_ROOT:-/opt/WebSphere/AppServers}
profile_root=${WAS_PROFILE_ROOT:-${was_root}/profiles}
role=${WAS_ROLE:?WAS_ROLE must be dmgr or node}
admin_user=${WAS_ADMIN_USER:-wsadmin}
password_file=/run/secrets/was_admin_password
authorized_key_file=/run/secrets/ansible_authorized_key

if [[ ! -s ${password_file} ]]; then
  echo "BOOTSTRAP_ERROR: missing ${password_file}. Run lab.ps1 init." >&2
  exit 30
fi
if [[ ! -s ${authorized_key_file} ]]; then
  echo "BOOTSTRAP_ERROR: missing ${authorized_key_file}. Run lab.ps1 init." >&2
  exit 31
fi

install -d -m 0700 -o ansible -g ansible /home/ansible/.ssh
install -m 0600 -o ansible -g ansible "${authorized_key_file}" /home/ansible/.ssh/authorized_keys
ssh-keygen -A >/dev/null
/usr/sbin/sshd -t

admin_password=$(tr -d '\r\n' < "${password_file}")

create_dmgr() {
  local dmgr_profile=${profile_root}/Dmgr01
  install -d -m 0755 -o was -g was "${dmgr_profile}"
  chown was:was "${dmgr_profile}"
  if [[ ! -x ${dmgr_profile}/bin/startManager.sh ]]; then
    echo "Creating genuine WebSphere deployment manager profile Dmgr01"
    runuser -u was -- "${was_root}/bin/manageprofiles.sh" -create \
      -profileName Dmgr01 \
      -profilePath "${dmgr_profile}" \
      -templatePath "${was_root}/profileTemplates/management" \
      -serverType DEPLOYMENT_MANAGER \
      -cellName "${WAS_CELL_NAME:-LabCell01}" \
      -nodeName "${WAS_DMGR_NODE:-DmgrNode01}" \
      -hostName "${HOSTNAME}" \
      -enableAdminSecurity true \
      -adminUserName "${admin_user}" \
      -adminPassword "${admin_password}" \
      -defaultPorts
  fi

  runuser -u was -- "${dmgr_profile}/bin/startManager.sh" || true
  for _ in $(seq 1 90); do
    if timeout 1 bash -c '</dev/tcp/127.0.0.1/8879' 2>/dev/null; then
      break
    fi
    sleep 2
  done
  if ! timeout 1 bash -c '</dev/tcp/127.0.0.1/8879' 2>/dev/null; then
    echo "BOOTSTRAP_ERROR: deployment manager SOAP port did not become ready." >&2
    exit 32
  fi

  local bootstrap_log=${dmgr_profile}/logs/lab-cell-bootstrap.log
  touch "${bootstrap_log}"
  chown was:was "${bootstrap_log}"
  chmod 0640 "${bootstrap_log}"
  runuser -u was -- nohup /opt/was-lab/bin/bootstrap-cell.sh \
    >> "${bootstrap_log}" 2>&1 &
}

create_node() {
  local node_name=${WAS_NODE_NAME:?WAS_NODE_NAME is required for a node}
  local node_profile=${profile_root}/AppSrv01
  install -d -m 0755 -o was -g was "${node_profile}"
  chown was:was "${node_profile}"
  if [[ ! -x ${node_profile}/bin/addNode.sh ]]; then
    echo "Creating genuine WebSphere managed profile AppSrv01 for ${node_name}"
    runuser -u was -- "${was_root}/bin/manageprofiles.sh" -create \
      -profileName AppSrv01 \
      -profilePath "${node_profile}" \
      -templatePath "${was_root}/profileTemplates/managed" \
      -nodeName "${node_name}" \
      -hostName "${HOSTNAME}" \
      -federateLater true
  fi

  if [[ ! -f ${node_profile}/.lab-federated ]]; then
    echo "Waiting for deployment manager before federating ${node_name}"
    for _ in $(seq 1 120); do
      if timeout 1 bash -c '</dev/tcp/was-dmgr/8879' 2>/dev/null; then
        break
      fi
      sleep 5
    done
    if ! timeout 1 bash -c '</dev/tcp/was-dmgr/8879' 2>/dev/null; then
      echo "BOOTSTRAP_ERROR: deployment manager is unavailable for ${node_name}." >&2
      exit 33
    fi
    runuser -u was -- "${node_profile}/bin/addNode.sh" was-dmgr 8879 \
      -username "${admin_user}" -password "${admin_password}"
    touch "${node_profile}/.lab-federated"
    chown was:was "${node_profile}/.lab-federated"
  else
    runuser -u was -- "${node_profile}/bin/startNode.sh" || true
  fi
}

case "${role}" in
  dmgr) create_dmgr ;;
  node) create_node ;;
  *) echo "BOOTSTRAP_ERROR: unsupported WAS_ROLE=${role}" >&2; exit 34 ;;
esac

unset admin_password
exec /usr/sbin/sshd -D -e
