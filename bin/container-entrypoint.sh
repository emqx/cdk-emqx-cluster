#!/bin/bash

set -euo pipefail

set -x
npm install -g aws-cdk
python3 -m venv .venv
source .venv/bin/activate
cd /opt/
pip3 install -r requirements.txt

exec "$@"
