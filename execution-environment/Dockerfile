FROM quay.io/ansible/awx-ee:24.6.1@sha256:89593d2a0268acacdbd1c075d8810ab50d961cf7769e36de19219bb6cb4efcc1

LABEL org.opencontainers.image.title="WebSphere ND lab AWX execution environment" \
      org.opencontainers.image.version="24.6.1-1"

USER root
RUN python3 -m pip install --no-cache-dir jmespath==1.0.1
USER 1000
