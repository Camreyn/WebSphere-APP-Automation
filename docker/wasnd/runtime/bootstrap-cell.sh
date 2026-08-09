#!/usr/bin/env bash
set -Eeuo pipefail

for attempt in $(seq 1 120); do
  set +e
  output=$(/opt/was-lab/bin/wsadmin-secure.sh \
    --password-file /run/secrets/was_admin_password \
    -f /opt/was-lab/bin/bootstrap_cell.py 2>&1)
  status=$?
  set -e
  printf '%s\n' "${output}"

  if [[ ${status} -eq 0 ]] && grep -q 'BOOTSTRAP_COMPLETE=true' <<< "${output}"; then
    exit 0
  fi
  if grep -q 'WAITING_FOR_NODES=true' <<< "${output}"; then
    sleep 5
    continue
  fi
  sleep 10
done

echo "BOOTSTRAP_ERROR: cell initialization did not complete before timeout." >&2
exit 42
