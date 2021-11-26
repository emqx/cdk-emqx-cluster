# 63f74cd56d17
FROM contino/aws-cdk:1.134.0

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
