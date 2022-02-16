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
    echo "test started at $(date -R)"
    # step 0: stop traffic
    echo "Stop Traffic"
    $BASEDIR/send_cmd.sh "$cluster" "stop_traffic" || echo "failed to stop traffic"

    # step 1: start traffic
    echo "Start Traffic"
    LB="lb.int.$cluster"

    ## sub clients: 200k, topic: $whildcard, rate: 5subs/s
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" "{\"Host\": [\"$LB\"], \"Command\":[\"sub\"],\"Prefix\":[\"cdkS1\"],\"Topic\":[\"root/%c/1/+/abc/#\"],\"Clients\":[\"200000\"],\"Interval\":[\"200\"]}"

    ## pub clients: 200k, topic: t1, rate:  pubs/s
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" "{\"Host\": [\"$LB\"], \"Command\":[\"pub\"],\"Prefix\":[\"cdkP1\"],\"Topic\":[\"t1\"],\"Clients\":[\"200000\"],\"Interval\":[\"200\"], \"PubInterval\":[\"1000\"]}"

    ## sub clients: 200, topic: t1, rate: 5 subs/s
    $BASEDIR/send_cmd.sh "$cluster" "start_traffic" "{\"Host\": [\"$LB\"], \"Command\":[\"sub\"],\"Prefix\":[\"cdkS2\"],\"Topic\":[\"t1\"],\"Clients\":[\"200\"],\"Interval\":[\"200\"]}"

    # step 2: sleep for 5mins for steady state
    sleep 300;
    ts_warmup_finish=$(date '+%s')
    echo "Warmup finish at ${ts_warmup_finish}"
    $BASEDIR/check_metrics.py "http://127.0.0.1:19090" "$ts_warmup_finish" 5m

    # step 3: inject faults
    echo "Inject fault: $fault:"
    jobid=$($BASEDIR/inject_fault.sh "$cluster" "$fault" | jq -r '.experiment.id');
    wait_fis_job_finish "$jobid"

    # step 4: wait for traffic to back to normal
    sleep 300;
    ts_recover_finish=$(date '+%s')
    echo "Recover finish at ${ts_recover_finish}"
    $BASEDIR/check_metrics.py "http://127.0.0.1:19090" "$ts_warmup_finish" 5m

    # step 5: collect logs
    echo "Collecting logs"
    $BASEDIR/send_cmd.sh "$cluster" "collect_logs" "$fault"|| die "stopped: collect_logs failed"

    echo "Stop Traffic"
    $BASEDIR/send_cmd.sh "$cluster" "stop_traffic" || echo "failed to stop traffic"

    echo "test finished at $(date -R)"
}

# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
cluster="$1"
tc_name="$2"

case "$tc_name" in
     all)
         for fault in ${ALL_FIS_FAULTS[*]};
         do
             gen_tc "$cluster" "$fault";
         done
         ;;
     list)
         # selected faults for test
         echo "Selected faults: ${ALL_FIS_FAULTS[*]}"
         ;;
     list-all)
         # list all available faults.
         list_all_faults "$cluster"
         ;;
     *)
         gen_tc "$cluster" "$tc_name"
         ;;
esac
