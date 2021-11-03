#!/usr/bin/env bash
set -euo pipefail
domain=$(dnsdomainname)

# emqtt bench escript will not start epmd, so we start it here
epmd -daemon

cd /root/
git clone -b "master" https://github.com/emqx/emqtt-bench.git
cd emqtt-bench
HOME=/root DIAGNOSTIC=1 make
