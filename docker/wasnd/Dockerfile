# syntax=docker/dockerfile:1.4

ARG UBI_IMAGE=registry.access.redhat.com/ubi9/ubi:9.6

FROM ${UBI_IMAGE} AS installer

ARG WAS_VERSION=9.0.5.28
ARG WAS_PACKAGE_ID=com.ibm.websphere.ND.v90
ARG JAVA_PACKAGE_ID=com.ibm.java.jdk.v8
ARG WAS_INSTALL_ROOT=/opt/WebSphere/AppServers

USER root

RUN dnf -y install \
      bash findutils gzip hostname libnsl libxcrypt-compat procps-ng tar unzip which \
    && dnf clean all \
    && rm -rf /var/cache/dnf

COPY artifacts/ibm/ /opt/ibm-media/
COPY docker/wasnd/install-was.sh /usr/local/sbin/install-was.sh

RUN chmod 0755 /usr/local/sbin/install-was.sh \
    && WAS_VERSION="${WAS_VERSION}" \
       WAS_PACKAGE_ID="${WAS_PACKAGE_ID}" \
       JAVA_PACKAGE_ID="${JAVA_PACKAGE_ID}" \
       WAS_INSTALL_ROOT="${WAS_INSTALL_ROOT}" \
       /usr/local/sbin/install-was.sh

FROM ${UBI_IMAGE} AS runtime

ARG WAS_VERSION=9.0.5.28
ARG WAS_INSTALL_ROOT=/opt/WebSphere/AppServers

LABEL org.opencontainers.image.title="Local WebSphere ND lab runtime" \
      org.opencontainers.image.description="Local-only UBI 9 runtime containing user-supplied licensed IBM WebSphere ND media" \
      org.opencontainers.image.version="${WAS_VERSION}"

USER root

RUN dnf -y install \
      bash findutils hostname iproute openssh-server procps-ng python3 shadow-utils sudo which \
      libnsl libxcrypt-compat \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && groupadd --gid 1001 was \
    && useradd --uid 1001 --gid was --home-dir /home/was --create-home --shell /bin/bash was \
    && groupadd --gid 1002 ansible \
    && useradd --uid 1002 --gid ansible --home-dir /home/ansible --create-home --shell /bin/bash ansible \
    && printf 'ansible ALL=(was) NOPASSWD: ALL\nansible ALL=(root) NOPASSWD: /usr/bin/test, /usr/bin/cat, /usr/bin/find, /usr/bin/tail\n' > /etc/sudoers.d/ansible-lab \
    && chmod 0440 /etc/sudoers.d/ansible-lab \
    && mkdir -p /run/sshd /opt/was-lab/bin /home/ansible/.ssh \
    && chmod 0700 /home/ansible/.ssh \
    && chown -R ansible:ansible /home/ansible/.ssh \
    && mkdir -p "${WAS_INSTALL_ROOT}/profiles" \
    && chown -R was:was "${WAS_INSTALL_ROOT}/profiles"

COPY --from=installer --chown=was:was ${WAS_INSTALL_ROOT}/ ${WAS_INSTALL_ROOT}/
COPY docker/wasnd/sshd_config /etc/ssh/sshd_config
COPY docker/wasnd/runtime/ /opt/was-lab/bin/

RUN chmod 0755 /opt/was-lab/bin/*.sh \
    && chmod 0644 /opt/was-lab/bin/*.py \
    && install -d -m 0755 -o was -g was \
         "${WAS_INSTALL_ROOT}/profiles/Dmgr01" \
         "${WAS_INSTALL_ROOT}/profiles/AppSrv01"

ENV WAS_INSTALL_ROOT=${WAS_INSTALL_ROOT} \
    WAS_PROFILE_ROOT=${WAS_INSTALL_ROOT}/profiles \
    PATH=${WAS_INSTALL_ROOT}/bin:${PATH}

EXPOSE 22 8879 9043 9060 9080 9443

ENTRYPOINT ["/opt/was-lab/bin/entrypoint.sh"]
