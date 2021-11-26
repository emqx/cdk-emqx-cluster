#!/bin/bash

set -euo pipefail

if [ "$1" = 'cdk' ]; then
    source /venv/bin/activate
fi

exec "$@"
