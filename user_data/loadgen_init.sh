#!/usr/bin/env bash
set -euo pipefail

cat >> /etc/sysctl.d/99-sysctl.conf <<EOF
net.core.rmem_default=262144000
net.core.wmem_default=262144000
net.core.rmem_max=262144000
net.core.wmem_max=262144000
net.ipv4.tcp_mem=378150000  504200000  756300000
EOF

sysctl -p

cd /root/
git clone -b "master" https://github.com/emqx/emqtt-bench.git
cd emqtt-bench
HOME=/root DIAGNOSTIC=1 make
