#!/bin/bash

set -euo pipefail

# for some reason, poetry creates a fresh shell if `poetry shell` is
# called at this point, and would require another `poetry install` to
# work...
source /root/.cache/pypoetry/virtualenvs/cdk-emqx-cluster-*/bin/activate

# If you run into a similar problem to the following:
# This CDK CLI is not compatible with the CDK library used by your application. Please upgrade the CLI to the latest version.
# (Cloud assembly schema version mismatch: Maximum schema version supported is 11.0.0, but found 15.0.0)
# run this workaround inside the container:
# npm uninstall -g aws-cdk
# npm install -g aws-cdk
# reference: https://github.com/aws/aws-cdk/issues/14738

exec "$@"
