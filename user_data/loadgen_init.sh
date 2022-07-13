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

$EMQTT_BENCH_SRC_CMD
pushd emqtt-bench
HOME=/root DIAGNOSTIC=1 make
popd

$EMQTTB_SRC_CMD
pushd emqttb
cp /root/emqtt-bench/rebar3 ./
env BUILD_WITHOUT_QUIC=1 ./rebar3 escriptize
popd

cluster=$(hostname -f | cut -d . -f 3)
aws s3 cp --recursive "s3://emqx-cdk-cluster/${cluster}/bin" /usr/local/bin/
