#!/usr/bin/env bash
#
# Helper script to verify all the faults are injected.
#
set -euo pipefail

BASEDIR=$(dirname "$0")
export AWS_PAGER=""

cluster=$1

# faults=( emqx-high-cpu-100
#          emqx-high-cpu-80
#          emqx-high-io-80
#          emqx-kill-proc
#          emqx-high-mem-80
#          emqx-distport-blackhole
#          emqx-latency-200ms
#          emqx-packet-loss-10 )


faults=(  emqx-high-cpu-80 )


## either completed for failed
wait_fis_job_finish() {
    local jobid=$1
    job_status=""
    while [[ $job_status != "completed" && $job_status != "failed" ]];
    do
        sleep 20;
        job_status=$(aws fis get-experiment --id="$jobid" | jq -r .experiment.state.status);
    done;
    echo "$job_status"
}

for fault in ${faults[*]};
do
    echo "Inject fault: $fault in cluster $cluster";
    ## start job and get jobid
    jobid=$($BASEDIR/inject_fault.sh $cluster $fault | jq -r '.experiment.id');
    status=$(wait_fis_job_finish $jobid)
    echo "[Finish] $jobid for $fault result: >> $status <<" ;
done
