#!/usr/bin/env bash
set -Eeuo pipefail

media_root=/opt/ibm-media
im_root=/opt/IBM/InstallationManager
shared_root=/opt/IBM/IMShared
was_root=${WAS_INSTALL_ROOT:-/opt/WebSphere/AppServers}
was_package=${WAS_PACKAGE_ID:-com.ibm.websphere.ND.v90}
java_package=${JAVA_PACKAGE_ID:-com.ibm.java.jdk.v8}
expected_version=${WAS_VERSION:-9.0.5.28}

mapfile -t installers < <(find "${media_root}" -maxdepth 2 -type f -name 'agent.installer.linux.gtk.x86_64*.zip' | sort)
if [[ ${#installers[@]} -ne 1 ]]; then
  echo "MEDIA_ERROR: expected exactly one IBM Installation Manager Linux x86-64 ZIP; found ${#installers[@]}." >&2
  exit 20
fi

mapfile -t repository_configs < <(find "${media_root}/repositories" -type f -name repository.config | sort)
if [[ ${#repository_configs[@]} -eq 0 ]]; then
  echo "MEDIA_ERROR: no repository.config files were found below artifacts/ibm/repositories." >&2
  exit 21
fi

repository_csv=$(IFS=,; printf '%s' "${repository_configs[*]}")
mkdir -p /tmp/im-installer "${im_root}" "${shared_root}" "${was_root}"
unzip -q "${installers[0]}" -d /tmp/im-installer

installer_command=/tmp/im-installer/installc
if [[ ! -x ${installer_command} ]]; then
  echo "MEDIA_ERROR: ${installers[0]} did not contain an executable installc." >&2
  exit 22
fi

"${installer_command}" \
  -acceptLicense \
  -installationDirectory "${im_root}" \
  -log /tmp/installation-manager-install.xml

imcl=${im_root}/eclipse/tools/imcl
if [[ ! -x ${imcl} ]]; then
  echo "INSTALL_ERROR: IBM Installation Manager imcl was not installed at ${imcl}." >&2
  exit 23
fi

"${imcl}" listAvailablePackages -repositories "${repository_csv}" -long > /tmp/available-packages.txt
if ! grep -Fq "${was_package}" /tmp/available-packages.txt; then
  echo "MEDIA_ERROR: repository set does not expose ${was_package}." >&2
  sed -n '1,160p' /tmp/available-packages.txt >&2
  exit 24
fi
if ! grep -Fq "${java_package}" /tmp/available-packages.txt; then
  echo "MEDIA_ERROR: repository set does not expose ${java_package}." >&2
  sed -n '1,160p' /tmp/available-packages.txt >&2
  exit 25
fi

"${imcl}" install "${was_package}" "${java_package}" \
  -repositories "${repository_csv}" \
  -installationDirectory "${was_root}" \
  -sharedResourcesDirectory "${shared_root}" \
  -acceptLicense \
  -showProgress \
  -log /tmp/was-nd-install.xml

version_info=${was_root}/bin/versionInfo.sh
if [[ ! -x ${version_info} ]]; then
  echo "INSTALL_ERROR: versionInfo.sh is missing after installation." >&2
  exit 26
fi

"${version_info}" > /tmp/version-info.txt
cat /tmp/version-info.txt

if ! grep -Eqi 'Network Deployment|ND' /tmp/version-info.txt; then
  echo "INSTALL_ERROR: installed product does not identify itself as Network Deployment." >&2
  exit 27
fi
if ! grep -Fq "${expected_version}" /tmp/version-info.txt; then
  echo "INSTALL_ERROR: expected WebSphere ${expected_version}; installed level differs." >&2
  exit 28
fi

rm -rf /tmp/im-installer /opt/ibm-media
