#!/usr/bin/env bash
set -euo pipefail
domain=$(dnsdomainname)

cd /root/
git clone -b "master" https://github.com/emqx/emqtt-bench.git
cd emqtt-bench
HOME=/root DIAGNOSTIC=1 make
