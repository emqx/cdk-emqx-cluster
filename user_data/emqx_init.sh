#!/bin/bash

domain=$(dnsdomainname)

if [ -b /dev/nvme1n1 ]; then
echo "Find extra data vol, format and mount..."
mkfs.ext4 -L emqx_data /dev/nvme1n1
mkdir -p /var/lib/emqx/
mount -L  emqx_data /var/lib/emqx/
fi


# Install emqx
# A)  install official version
wget https://www.emqx.io/downloads/broker/v4.3.0/emqx-ubuntu20.04-4.3.0-amd64.deb
#sudo apt install ./emqx-ubuntu20.04-4.3.0-amd64.deb


cd /root/
#git clone https://github.com/emqx/emqx

## use private branch which inc this workaround
# https://github.com/qzhuyan/emqx/commit/6fcd35bf8db523a5f39fd1b9c5ba181b7d3ffb98
git clone -b perf-test/william/quic-0.0.9 https://github.com/qzhuyan/emqx
cd emqx
HOME=/root make emqx-pkg
dpkg -i ./_packages/emqx/*.deb

nodename="emqx@`hostname -f`"
cat <<EOF >> /etc/emqx/emqx.conf
node {
 name: $nodename
}

cluster {
 discovery_strategy = etcd

 etcd {
   server: "http://etcd0.${domain}:2379"
   ssl.enable: false
 }
}

listeners.tcp.default {
 acceptors: 128
}

rate_limit {
 max_conn_rate = infinity
 conn_messages_in = infinity
 conn_bytes_in = infinity
}

prometheus {
    push_gateway_server = "http://lb.${domain}:9091"
    interval = "15s"
    enable = true
}

gateway.exproto {
server {
  bind = 9101
 }
}


rate_limit {
  ## Maximum connections per second.
  ##
  ## @doc zones.<name>.max_conn_rate
  ## ValueType: Number | infinity
  ## Default: 1000
  ## Examples:
  ##   max_conn_rate: 1000
  max_conn_rate = infinity

  ## Message limit for the a external MQTT connection.
  ##
  ## @doc rate_limit.conn_messages_in
  ## ValueType: String | infinity
  ## Default: infinity
  ## Examples: 100 messages per 10 seconds.
  ##   conn_messages_in: "100,10s"
  conn_messages_in = infinity

  ## Limit the rate of receiving packets for a MQTT connection.
  ## The rate is counted by bytes of packets per second.
  ##
  ## The connection won't accept more messages if the messages come
  ## faster than the limit.
  ##
  ## @doc rate_limit.conn_bytes_in
  ## ValueType: String | infinity
  ## Default: infinity
  ## Examples: 100KB incoming per 10 seconds.
  ##   conn_bytes_in: "100KB,10s"
  ##
  conn_bytes_in = infinity
}

EOF

sudo emqx start
