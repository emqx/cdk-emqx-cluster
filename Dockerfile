# sha256:c2fda87e52bdedc1e3424e88187e24722793b4dc218e2be91d4501295387a02e
FROM ghcr.io/emqx/docker-aws-cdk/aws-cdk:master

RUN curl -sSL https://install.python-poetry.org | POETRY_VERSION=1.1.14 python3 -
ENV PATH=/root/.local/bin:$PATH
WORKDIR /setup
COPY pyproject.toml /setup/pyproject.toml
COPY poetry.lock /setup/poetry.lock
# install only cdk-emqx-cluster's deps for better docker caching
RUN poetry install --no-root
COPY README.md /setup/
RUN mkdir -p /setup/cdk_emqx_cluster
COPY cdk_emqx_cluster /setup/cdk_emqx_cluster
COPY bin/container-entrypoint.sh /container-entrypoint.sh
# install cdk-emqx-cluster itself
RUN poetry install
ENTRYPOINT ["/container-entrypoint.sh"]
