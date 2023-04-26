# This file is part of the emqx init script that will be appened to the user-data part

cat >> /etc/sysctl.d/99-sysctl.conf <<EOF
net.core.somaxconn=32768
net.ipv4.tcp_max_syn_backlog=16384
net.core.netdev_max_backlog=16384
net.core.optmem_max=16777216
net.ipv4.tcp_rmem=1024 4096 16777216
net.ipv4.tcp_wmem=1024 4096 16777216
net.ipv4.tcp_max_tw_buckets=1048576
net.ipv4.tcp_fin_timeout=15
net.core.rmem_default=262144000
net.core.wmem_default=262144000
net.core.rmem_max=262144000
net.core.wmem_max=262144000
net.ipv4.tcp_mem=378150000  504200000  756300000
EOF

sysctl -p

install_docker() {
  # we need docker to pull and use emqx-builder
  apt update
  apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

  apt update
  apt install -y docker-ce docker-ce-cli containerd.io

  docker pull "$EMQX_BUILDER_IMAGE"
}

disable_docker() {
  systemctl stop docker
  systemctl disable docker
}

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
    install_docker
    cd emqx
    docker run --rm -i \
           -v "$PWD":/emqx \
           -w /emqx \
           -e EMQX_NAME="emqx" \
           -e HOME="/root" \
           "$EMQX_BUILDER_IMAGE" \
           bash -c "make $EMQX_BUILD_PROFILE"
    dpkg -i ./_packages/emqx*/*.deb
    disable_docker
  fi
  popd
}

maybe_config_overrides_v5() {
  case "${EMQX_CDK_DB_BACKEND}" in
    rlog)
      case "${EMQX_CDK_DB_BACKEND_ROLE}" in
        core)
          cat >> /etc/emqx/emqx.conf <<EOF
node {
  db_backend = "rlog"
  db_role = "core"
}
EOF
          ;;

      replicant)
        cat >> /etc/emqx/emqx.conf <<EOF
node {
  db_backend = "rlog"
  db_role = "replicant"
}
cluster {
  core_nodes = "${EMQX_CDK_CORE_NODES}"
}
EOF
        ;;
      esac
      ;;
    mnesia)
      cat >> /etc/emqx/emqx.conf <<EOF
node {
  db_backend = "mnesia"
  db_role = "core"
}
EOF
      ;;
  esac
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
  limiter.connection.rate = infinity
  limiter.message_in.rate = infinity
  limiter.message_routing.rate = infinity
  limiter.bytes_in.rate = infinity
  tcp_options {
  buffer = 1KB
  recbuf = 1KB
  sndbuf = 1KB
  }
}

listeners.ssl.default {
  acceptors: 128
  max_connections: infinity
  limiter.connection.rate = infinity
  limiter.message_in.rate = infinity
  limiter.message_routing.rate = infinity
  limiter.bytes_in.rate = infinity
  tcp_options {
  buffer = 1KB
  recbuf = 1KB
  sndbuf = 1KB
  }
}

listeners.quic.default {
  enabled = true
  bind = "0.0.0.0:14567"
  max_connections = infinity
  keyfile = "/etc/emqx/certs/key.pem"
  certfile = "/etc/emqx/certs/cert.pem"
  limiter.connection.rate = infinity
  limiter.message_in.rate = infinity
  limiter.message_routing.rate = infinity
  limiter.bytes_in.rate = infinity
}

conn_congestion {
    enable_alarm = false
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

  handler {
    address = "http://127.0.0.1:9001"
  }
}

api_key {
  bootstrap_file = "/tmp/emqx_bootstrap.txt"
}

limiter.connection.rate = infinity
limiter.message_in.rate = infinity
limiter.message_routing.rate = infinity
limiter.bytes_in.rate = infinity

sysmon.top {
  db_hostname = "lb.${domain}"
  db_username = "system_monitor"
  db_password = "${EMQX_CDK_POSTGRES_PASS}"
  max_procs = 3000000
  sample_interval = 5s
}

node {
  max_ports = 1010000
  process_limit = 1010000
}

zone {
 default {
  conn_congestion.enable_alarm = false
  force_gc = false
 }
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
listener.tcp.external.max_connections = 100000000
listener.ssl.external.max_conn_rate = 5000
listener.ssl.external.acceptors = 128
listener.ssl.external.max_connections = 100000000
rpc.tcp_client_num=8
rpc.socket_sndbuf=4MB
rpc.socket_recbuf=4MB
rpc.socket_buffer=8MB
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

install_helpers() {
  cluster=$(hostname -f | cut -d . -f 3)
  aws s3 cp --recursive "s3://emqx-cdk-cluster/${cluster}/bin" /usr/local/bin/
}

bootstrap_api_user() {
  echo "cdkuser:N0tpublic" > /tmp/emqx_bootstrap.txt
}

# Assume we have emqx src in PWD
# emqx src is either deb file or git src tree

maybe_mount_data
maybe_install_from_deb
maybe_install_from_src

EMQX_VERSION=$(dpkg -s emqx emqx-ee emqx-enterprise | grep Version | awk '{print $2}')

case "${EMQX_VERSION}" in
  4*)
    config_overrides_v4
    ;;
  5*)
    config_overrides_v5
    maybe_config_overrides_v5
    ;;
  *)
    echo "Unknown EMQX_VERSION: ${EMQX_VERSION}"
esac

maybe_install_license
install_helpers
bootstrap_api_user
systemctl start emqx
