#!/usr/bin/env bash
set -Eeuo pipefail

was_root=${WAS_INSTALL_ROOT:-/opt/WebSphere/AppServers}
profile_name=${WAS_DMGR_PROFILE_NAME:-Dmgr01}
profile_root=${was_root}/profiles/${profile_name}
credential_file=
password_file=

case ${1:-} in
  --credential-file)
    credential_file=${2:?credential file path required}
    shift 2
    ;;
  --password-file)
    password_file=${2:?password file path required}
    shift 2
    ;;
  *)
    echo "Usage: wsadmin-secure.sh (--credential-file FILE | --password-file FILE) [wsadmin arguments...]" >&2
    exit 40
    ;;
esac

if [[ -n ${credential_file} ]]; then
  mapfile -t credentials < "${credential_file}"
  [[ ${#credentials[@]} -ge 2 ]] || { echo "Credential file must contain username and password lines." >&2; exit 41; }
  username=${credentials[0]%$'\r'}
  password=${credentials[1]%$'\r'}
else
  username=${WAS_ADMIN_USER:-wsadmin}
  password=$(tr -d '\r\n' < "${password_file}")
fi

props=$(mktemp /tmp/soap.client.XXXXXX.props)
cleanup() {
  rm -f "${props}"
}
trap cleanup EXIT
chmod 0600 "${props}"
cp "${profile_root}/properties/soap.client.props" "${props}"
cat >> "${props}" <<EOF
com.ibm.SOAP.securityEnabled=true
com.ibm.SOAP.loginSource=none
com.ibm.SOAP.loginUserid=${username}
com.ibm.SOAP.loginPassword=${password}
EOF

encoder=${was_root}/bin/PropFilePasswordEncoder.sh
if [[ -x ${encoder} ]]; then
  "${encoder}" "${props}" com.ibm.SOAP.loginPassword -noBackup -profileName "${profile_name}" >/dev/null
fi

unset password credentials
set +e
"${profile_root}/bin/wsadmin.sh" \
  -lang jython \
  -conntype SOAP \
  -host localhost \
  -port 8879 \
  -javaoption "-Dcom.ibm.SOAP.ConfigURL=file:${props}" \
  "$@"
status=$?
set -e
exit "${status}"
