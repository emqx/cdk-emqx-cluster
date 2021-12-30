# sha256:c2fda87e52bdedc1e3424e88187e24722793b4dc218e2be91d4501295387a02e
FROM ghcr.io/emqx/docker-aws-cdk/aws-cdk:master

RUN python3 -m venv /venv
COPY requirements.txt /setup/requirements.txt
COPY setup.py /setup/setup.py
COPY README.md /setup/
COPY cdk_emqx_cluster /setup/cdk_emqx_cluster
RUN cd /setup/ \
    && source /venv/bin/activate \
    && pip3 install --upgrade pip \
    && pip3 install -r requirements.txt
COPY bin/container-entrypoint.sh /container-entrypoint.sh
ENTRYPOINT ["/container-entrypoint.sh"]
