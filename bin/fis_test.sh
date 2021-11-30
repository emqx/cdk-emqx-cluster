#!/usr/bin/env bash
#
# Helper script to verify all the faults are injected.
#
set -euo pipefail

BASEDIR=$(dirname "$0")
source ${BASEDIR}/fis_lib.sh
export AWS_PAGER=""

cluster=$1

for fault in ${ALL_FIS_FAULTS[*]};
do
    echo "Inject fault: $fault in cluster $cluster";
    ## start job and get jobid
    jobid=$($BASEDIR/inject_fault.sh $cluster $fault | jq -r '.experiment.id');
    status=$(wait_fis_job_finish $jobid)
    echo "[Finish] $jobid for $fault result: >> $status <<" ;
done
