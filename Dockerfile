#  sha256:8d6f89f74e8051a07204d65ac3f4d71e668f628415737397d3b50e6571c49485
FROM ghcr.io/emqx/docker-aws-cdk/aws-cdk:2.27.0

RUN python3 -m venv /venv
COPY requirements.txt /setup/requirements.txt
COPY setup.py /setup/setup.py
COPY README.md /setup/
RUN mkdir -p /setup/cdk_emqx_cluster
RUN cd /setup/ \
    && source /venv/bin/activate \
    && pip3 install --upgrade pip \
    && pip3 install -r requirements.txt
COPY cdk_emqx_cluster /setup/cdk_emqx_cluster
COPY bin/container-entrypoint.sh /container-entrypoint.sh
ENTRYPOINT ["/container-entrypoint.sh"]
