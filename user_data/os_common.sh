#!/bin/bash

echo "session required pam_limits.so" >> /etc/pam.d/common-session
echo "*      soft    nofile      10000000"  >> /etc/security/limits.conf
echo "*      hard    nofile      100000000"  >> /etc/security/limits.conf


cat >> /etc/sysctl.d/99-sysctl.conf <<EOF
net.ipv4.tcp_tw_reuse=1
fs.nr_open=1000000000
net.ipv4.ip_local_port_range=1025 65534
net.ipv4.udp_mem=74583000 499445000 749166000
EOF

sysctl -p

## Install OTP
apt update
apt install -y make wget gnupg2 git build-essential curl cmake debhelper tmux libodbc1 awscli net-tools linux-tools-common linux-tools-aws

#snap install cmake --classic
#wget -O - https://packages.erlang-solutions.com/ubuntu/erlang_solutions.asc | sudo apt-key add -
#echo "deb https://packages.erlang-solutions.com/ubuntu focal contrib" | tee /etc/apt/sources.list.d/els.list
#apt update
#apt install -y esl-erlang=1:25.3-1
#
curl -fsSL https://packages.erlang-solutions.com/ubuntu/erlang_solutions.asc | sudo gpg --dearmor -o /etc/apt/trusted.gpg.d/erlang.gpg
apt update
apt install erlang

## Install node exporter
case $(uname -m) in
    aarch64)
    arch=arm64
    ;;
    *)
    arch=amd64
esac
useradd --no-create-home --shell /bin/false node_exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.1.2/node_exporter-1.1.2.linux-$arch.tar.gz
tar zxvf node_exporter-1.1.2.linux-$arch.tar.gz
mv node_exporter-1.1.2.linux-$arch/node_exporter /usr/local/bin/
chown node_exporter:node_exporter /usr/local/bin/node_exporter
mkdir -p /prometheus/metrics
chown node_exporter:node_exporter /prometheus/metrics

cat <<EOF > /lib/systemd/system/node_exporter.service
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=node_exporter
Group=node_exporter
ExecStart=/usr/local/bin/node_exporter --collector.textfile.directory=/prometheus/metrics
Restart=always
RestartSec=10s
NotifyAccess=all

[Install]
WantedBy=multi-user.target
EOF

systemctl enable node_exporter
systemctl start node_exporter

apt-add-repository ppa:lttng/stable-2.13
apt-get update
apt-get install -y lttng-tools lttng-modules-dkms babeltrace liblttng-ust-dev
