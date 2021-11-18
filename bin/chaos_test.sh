#!/bin/bash
###############################################################################
# We put chaos tests script here and hopefully we could reuse these scripts in k8s env
###############################################################################

set -e

BASEDIR=$(dirname "$0")
export AWS_PAGER=""

die() {
    echo "$@" >&2
    exit 1
}

# emqx node stop
tc_1() {
    cluster=$1
    # step 1: start traffic
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" || die "stopped: start traffic failed"
    # step 2: sleep for 5mins for steady state
    sleep 300;
    # step 3: send command to shutdown emqx node for 1 min.
    $BASEDIR/inject_fault.sh "$cluster" "emqx-node-shutdown" || die "stopped: fault injection failed"
    # step 4: wait for traffic to back to normal
    sleep 300;
    # step 5: collect logs
    $BASEDIR/send_cmd.sh "$cluster" "collect_logs" || die "stopped: collect_logs failed"

    echo "test finished"
}

# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
tc_name=$2

$tc_name $1
