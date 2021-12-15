#!/bin/bash

################################################################################
# This script is used to send a command to the node with AWS SSM
# commands are cluster wide, it will self pick the target nodes.
#
# supported commands:
#  - start_traffic
#     start background traffic on the node (pub and sub)
#  - collect_logs
#     collect logs from the emqx nodes and copy it to S3 bucket
################################################################################


# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
cluster=$1

# CdkChaosTests.ControlCmd,
# scripts are under cdk_emqx_cluster/ssm_docs/
command=$2

shift 2;

die() {
    echo $1
    exit 1;
}

help() {
    echo "$(basename $0) cluster cmd"
    echo "available cmds: stop_traffic, start_traffic, collect_logs"
}

wait_for_cmd_finish() {
    local jobid=$1
    local interval=${2:-20}
    local job_status=""
    local result=""
    # wait for the result either success for failed
    while [[ $result != "true" ]];
    do
        sleep $interval;
        job_status=$(aws ssm list-command-invocations --command-id="$jobid");
        result=$(echo "$job_status" | jq -r '.CommandInvocations | map(.Status == "Success" or .Status== "Failed") | all');
    done;
    echo "$job_status"
    ## ensure
    if [[ "true" == $(echo "$job_status" | jq -r '.CommandInvocations | map(.Status == "Success")  | all') ]]; then
        return 0;
    else
        return 1;
    fi
}

if [ -z "$cluster" ]; then
    help
    die "cluster not set";
fi

doc_name=$(aws ssm list-documents --filters "Key=tag:cluster,Values=$cluster" --filters "Key=tag:cmd,Values=$command" | jq -r '.DocumentIdentifiers[0].Name')
if [[ "$doc_name" == "null" || ! $? ]]; then
    help
    die "command '$command' not found, did you deploy the CdkChaosTests Stack?"
fi

case $command in
    "stop_traffic")
        jobid=$(aws ssm send-command --document-name "$doc_name" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0" |  jq -r .Command.CommandId)
        wait_for_cmd_finish "$jobid" 1
        ;;

    "start_traffic")
        # supply command parameters and targets
        param=$1;
        jobid=$(aws ssm send-command --document-name "$doc_name" \
            --parameters "$param" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0" |  jq -r .Command.CommandId)
        wait_for_cmd_finish "$jobid"
        ;;

    "collect_logs")
        logname_prefix=$1;
        jobid=$(aws ssm send-command --document-name "$doc_name" \
            --parameters "{\"Bucket\":[\"emqx-cdk-cluster\"],\"Path\":[\"$cluster\"], \"Prefix\":[\"$logname_prefix\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"emqx\"]}]" \
            --timeout-seconds 600 --max-concurrency "50" --max-errors "0" |  jq -r .Command.CommandId)
        wait_for_cmd_finish "$jobid"
        ;;
    *)
        help
        die "unknown command $command"
        ;;
esac
