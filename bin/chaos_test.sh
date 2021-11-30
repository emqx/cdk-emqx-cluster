#!/bin/bash
###############################################################################
# We put chaos tests script here and hopefully we could reuse these scripts in k8s env
# To run chaos test the stack called CDKchaosTest should be deployed.
###############################################################################

set -e

BASEDIR=$(dirname "$0")
source $BASEDIR/fis_lib.sh
export AWS_PAGER=""

die() {
    echo "$@" >&2
    exit 1
}


gen_tc() {
    cluster=$1
    fault=$2
    # step 1: start traffic
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" || die "stopped: start traffic failed"
    # step 2: sleep for 5mins for steady state
    sleep 300;
    # step 3: send command to shutdown emqx node for 1 min.
    $BASEDIR/inject_fault.sh "$cluster" "$fault" || die "stopped: fault injection failed"
    # step 4: wait for traffic to back to normal
    sleep 300;
    # step 5: collect logs
    $BASEDIR/send_cmd.sh "$cluster" "collect_logs" || die "stopped: collect_logs failed"

    echo "test finished"
}


# emqx node stop
tc_1() {
    cluster=$1
    # step 0: stop loadgen
    $BASEDIR/send_cmd.sh "$cluster" "stop_traffic" || die "stopped: stop traffic failed"
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

tc_2() {
    cluster=$1
    fault="emqx-high-cpu-80"
    # step 0: stop loadgen
    $BASEDIR/send_cmd.sh "$cluster" "stop_traffic" || die "stopped: stop traffic failed"
    # step 1: start traffic
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" || die "stopped: start traffic failed"
    # step 2: sleep for 5mins for steady state
    sleep 300;
    # step 3: send command to shutdown emqx node for 1 min.
    $BASEDIR/inject_fault.sh "$cluster" "$fault" || die "stopped: fault injection failed"
    # step 4: wait for traffic to back to normal
    sleep 300;
    # step 5: collect logs
    $BASEDIR/send_cmd.sh "$cluster" "collect_logs" || die "stopped: collect_logs failed"

    echo "test finished"
}


tc_3() {
    cluster=$1
    fault="emqx-high-io-80"
    # step 0: stop loadgen
    $BASEDIR/send_cmd.sh "$cluster" "stop_traffic" || die "stopped: stop traffic failed"
    # step 1: start traffic
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" || die "stopped: start traffic failed"
    # step 2: sleep for 5mins for steady state
    sleep 300;
    # step 3: send command to shutdown emqx node for 1 min.
    $BASEDIR/inject_fault.sh "$cluster" "$fault" || die "stopped: fault injection failed"
    # step 4: wait for traffic to back to normal
    sleep 300;
    # step 5: collect logs
    $BASEDIR/send_cmd.sh "$cluster" "collect_logs" || die "stopped: collect_logs failed"

    echo "test finished"
}

# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
cluster="$1"
tc_name="$2"

case $tc_name in
     all)
         for fault in ${ALL_FIS_FAULTS[*]};
         do
             gen_tc "$cluster" "$fault"
         done
         ;;
     *)
         $tc_name $cluster
esac
