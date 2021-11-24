#!/bin/bash

sudo bash -c 'echo "session required pam_limits.so" >> /etc/pam.d/common-session'
sudo bash -c 'echo "*      soft    nofile      2000000"  >> /etc/security/limits.conf'
sudo bash -c 'echo "*      hard    nofile      2000000"  >> /etc/security/limits.conf'

echo "net.ipv4.tcp_tw_reuse=1" >>  /etc/sysctl.d/99-sysctl.conf
echo "fs.nr_open=8000000" >>  /etc/sysctl.d/99-sysctl.conf
echo 'net.ipv4.ip_local_port_range="1025 65534"' >>  /etc/sysctl.d/99-sysctl.conf
echo 'net.ipv4.udp_mem="74583000 499445000 749166000"' >> /etc/sysctl.d/99-sysctl.conf

sysctl -w fs.nr_open=8000000
sysctl -w net.ipv4.tcp_tw_reuse=1
sysctl -w net.ipv4.ip_local_port_range="1025 65534"
sysctl -w net.ipv4.udp_mem="74583000 499445000 749166000"

## Install OTP
apt update
apt install -y make wget gnupg2 git build-essential curl cmake debhelper tmux libodbc1 awscli

#snap install cmake --classic
wget -O - https://packages.erlang-solutions.com/ubuntu/erlang_solutions.asc | sudo apt-key add -
echo "deb https://packages.erlang-solutions.com/ubuntu focal contrib" | tee /etc/apt/sources.list.d/els.list
apt update
apt install -y esl-erlang=1:23.3.4.5-1

## Install node exporter
useradd --no-create-home --shell /bin/false node_exporter
wget https://github.com/prometheus/node_exporter/releases/download/v1.1.2/node_exporter-1.1.2.linux-amd64.tar.gz
tar zxvf node_exporter-1.1.2.linux-amd64.tar.gz
mv node_exporter-1.1.2.linux-amd64/node_exporter /usr/local/bin/
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
