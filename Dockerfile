# sha256:c2fda87e52bdedc1e3424e88187e24722793b4dc218e2be91d4501295387a02e
FROM ghcr.io/emqx/docker-aws-cdk/aws-cdk:master

RUN python3 -m venv /venv && \
    . /venv/bin/activate && \
    pip3 install poetry==1.1.14
WORKDIR /setup
COPY pyproject.toml /setup/pyproject.toml
COPY poetry.lock /setup/poetry.lock
# install only cdk-emqx-cluster's deps for better docker caching
RUN . /venv/bin/activate && \
    poetry install --no-root
COPY README.md /setup/
RUN mkdir -p /setup/cdk_emqx_cluster
COPY cdk_emqx_cluster /setup/cdk_emqx_cluster
COPY bin/container-entrypoint.sh /container-entrypoint.sh
# install cdk-emqx-cluster itself
RUN . /venv/bin/activate && \
    poetry install
ENTRYPOINT ["/container-entrypoint.sh"]
