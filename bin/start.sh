#/bin/bash
set -eox pipefail
[ -z ${CDK_EMQX_CLUSTERNAME+x} ] && CDK_EMQX_CLUSTERNAME=$(git config --get user.name)
docker run -e CDK_EMQX_CLUSTERNAME=${CDK_EMQX_CLUSTERNAME} --rm -it \
       -v ~/.aws:/root/.aws -v $(pwd):/opt/ contino/aws-cdk \
       /opt/bin/container-entrypoint.sh
