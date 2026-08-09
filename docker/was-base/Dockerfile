# syntax=docker/dockerfile:1.4

ARG IBM_WAS_IMAGE=icr.io/appcafe/websphere-traditional:9.0.5.28
FROM ${IBM_WAS_IMAGE}

LABEL org.opencontainers.image.title="WebSphere traditional Base ILAN lab runtime" \
      org.opencontainers.image.description="SSH-enabled wrapper around IBM's official traditional WebSphere 9.0.5.28 ILAN image" \
      org.opencontainers.image.version="9.0.5.28"

USER root

RUN dnf -y install \
      findutils hostname openssh-server procps-ng python3 shadow-utils sudo \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && groupadd --gid 1002 ansible \
    && useradd --uid 1002 --gid ansible --home-dir /home/ansible --create-home --shell /bin/bash ansible \
    && passwd -d ansible \
    && printf 'ansible ALL=(was) NOPASSWD: ALL\n' > /etc/sudoers.d/ansible-was-base \
    && chmod 0440 /etc/sudoers.d/ansible-was-base \
    && install -d -m 0755 /run/sshd \
    && install -d -m 0700 -o ansible -g ansible /home/ansible/.ssh \
    && install -d -m 0755 /opt/was-lab/bin

COPY docker/wasnd/sshd_config /etc/ssh/sshd_config
COPY docker/was-base/config/ /etc/websphere/
COPY docker/was-base/entrypoint.sh /opt/was-lab/bin/base-entrypoint.sh

RUN chmod 0755 /opt/was-lab/bin/base-entrypoint.sh

ENV PROFILE_NAME=AppSrv01 \
    SERVER_NAME=server1 \
    ADMIN_USER_NAME=wsadmin \
    UPDATE_HOSTNAME=true \
    EXTRACT_PORT_FROM_HOST_HEADER=false \
    ENABLE_BASIC_LOGGING=true

EXPOSE 22 8880 9043 9060 9080 9443

ENTRYPOINT ["/opt/was-lab/bin/base-entrypoint.sh"]
