# This file is part of the emqx init script that will be appened to the user-data part
maybe_mount_data() {
  if [ -b /dev/nvme1n1 ]; then
  echo "Find extra data vol, format and mount..."
  mkfs.ext4 -L emqx_data /dev/nvme1n1
  mkdir -p /var/lib/emqx/
  mount -L  emqx_data /var/lib/emqx/
  fi
}

maybe_install_from_deb() {
  if [ -f *.deb ]; then
    echo "Find deb file, install from deb package..."
    dpkg -i emqx*.deb
  fi
}

maybe_install_from_src() {
  pushd ./
  if [ -d emqx ]; then
    echo "Find emqx source code, install from source code..."
    cd emqx
    HOME=/root make emqx-pkg
    dpkg -i ./_packages/emqx/*.deb
  fi
  popd
}

maybe_cluster_config_overrides_v5() {
  if [[ "${EMQX_CDK_DB_BACKEND}" = "rlog" ]]
  then
    case "${EMQX_CDK_DB_BACKEND_ROLE}" in
      core)
        cat > /etc/emqx/cluster-override.conf <<EOF
db {
  backend = "rlog"
  role = "core"
}
EOF
        ;;

      replicant)
        cat > /etc/emqx/cluster-override.conf <<EOF
db {
  backend = "rlog"
  role = "replicant"
  core_nodes = "${EMQX_CDK_CORE_NODES}"
}
EOF
        ;;
    esac
  fi
}

config_overrides_v5() {
  domain=$(dnsdomainname)
  nodename="emqx@`hostname -f`"
  cat <<EOF >> /etc/emqx/vm.args
+P 16777216
+Q 16777216
+Muacnl 10
+hms 64
EOF
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
  max_connections: infinity
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

system_monitor {
  db_hostname = "lb.${domain}"
  db_username = "system_monitor"
  db_password = "system_monitor_password"
}

EOF
}


config_overrides_v4() {
  domain=$(dnsdomainname)
  echo "## ========= cloud user_data start  ===========##" >> /etc/emqx/emqx.conf
  echo "node.name = emqx@`hostname -f`" >> /etc/emqx/emqx.conf

  cat <<EOF >> /etc/emqx/emqx.conf
cluster.discovery = etcd
cluster.etcd.server = http://etcd0.${domain}:2379
listener.tcp.external.max_conn_rate = 5000
listener.tcp.external.acceptors = 128
## ========= cloud user_data end  ===========##
EOF

  echo "prometheus.push.gateway.server = http://lb.${domain}:9091" >> /etc/emqx/plugins/emqx_prometheus.conf
  echo "{emqx_prometheus, true}." >> /var/lib/emqx/loaded_plugins
}

maybe_install_license() {
  local cluster=$(hostname -f | cut -d . -f 3)
  local lic="s3://emqx-cdk-cluster/$cluster/emqx.lic"
  if aws s3 ls "$lic"; then
    aws s3 cp "$lic" /etc/emqx/
  fi
}

# Assume we have emqx src in PWD
# emqx src is either deb file or git src tree

maybe_mount_data
maybe_install_from_deb
maybe_install_from_src

EMQX_VERSION=$(dpkg -s emqx emqx-ee | grep Version | awk '{print $2}')

case "${EMQX_VERSION}" in
  4*)
    config_overrides_v4
    ;;
  5*)
    config_overrides_v5
    maybe_cluster_config_overrides_v5
    ;;
  *)
    echo "Unknown EMQX_VERSION: ${EMQX_VERSION}"
esac

maybe_install_license
systemctl start emqx
