# sha256:57cc4f3d7c9e0ccc3a4d8d55017e4878c5a0713638645ede9b56bf91d9cec128
FROM ghcr.io/emqx/docker-aws-cdk/aws-cdk:2.82.0

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
