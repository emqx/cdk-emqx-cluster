#!/bin/bash --init-file
npm install -g aws-cdk
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
