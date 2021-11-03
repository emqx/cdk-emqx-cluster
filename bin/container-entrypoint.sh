#!/bin/bash --init-file
npm install -g aws-cdk
python3 -m venv .venv
cd /opt/
source .venv/bin/activate
pip3 install -r requirements.txt
