#!/usr/bin/env bash
set -euo pipefail

###
### helper library for using FIS
###

ALL_FIS_FAULTS=( emqx-node-shutdown
                 emqx-high-cpu-100
                 emqx-high-cpu-80
                 emqx-high-io-80
                 emqx-kill-proc
                 emqx-high-mem-80
                 emqx-distport-blackhole
                 emqx-latency-200ms
                 emqx-packet-loss-10 )
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
