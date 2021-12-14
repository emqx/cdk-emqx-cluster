#!/usr/bin/env bash

die() {
    echo "$@" >&2
    exit 1
}

kafka_get_cluser_arn() {
    local cluster=$1;
    aws kafka list-clusters --cluster-name-filter="${cluster}-kafka" | jq -r '.ClusterInfoList[].ClusterArn'
}

kafka_get_cluser_zks() {
    local cluster=$1;
    aws kafka list-clusters --cluster-name-filter="${cluster}-kafka" | jq -r '.ClusterInfoList[].ZookeeperConnectString'

}

kafka_get_cluser_brokers() {
    local cluster=$1;
    local arn=$(kafka_get_cluser_arn $cluster)

    if [ -z "$arn" ]; then
        die "error: arn for $cluster not found"
    fi
    aws kafka get-bootstrap-brokers --cluster-arn "$arn"
}

kafka_get_cluser_brokers_tls() {
    local cluster=$1;
    kafka_get_cluser_brokers "$cluster" | jq -r '.BootstrapBrokerStringTls'

}

kafka_get_cluser_brokers_plaintext() {
    local cluster=$1;
    kafka_get_cluser_brokers "$cluster" | jq -r '.BootstrapBrokerString'
}

cluster=$1
cmd=$2

"$cmd" "$cluster"
