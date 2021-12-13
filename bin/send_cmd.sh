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

if [ -z "$cluster" ]; then
    help
    die "cluster not set";
fi

doc_name=$(aws ssm list-documents --filters "Key=tag:cluster,Values=$cluster" --filters "Key=tag:cmd,Values=$command" | jq -r '.DocumentIdentifiers[0].Name')
if [[ "$doc_name" == "null" || ! $? ]]; then
    die "command '$command' not found, did you deploy the CdkChaosTests Stack?"
fi

case $command in
    "stop_traffic")
        aws ssm send-command --document-name "$doc_name" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0"
        ;;

    "start_traffic")
        # supply command parameters and targets
        LB="lb.int.$cluster"
        aws ssm send-command --document-name "$doc_name" \
            --parameters "{\"Host\": [\"$LB\"], \"Command\":[\"sub\"],\"Prefix\":[\"cdk\"],\"Topic\":[\"t1\"],\"Clients\":[\"200000\"],\"Interval\":[\"200\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0"

        aws ssm send-command --document-name "$doc_name" \
            --parameters "{\"Host\": [\"$LB\"], \"Command\":[\"pub\"],\"Prefix\":[\"cdk\"],\"Topic\":[\"t1\"],\"Clients\":[\"200000\"],\"Interval\":[\"200\"], \"PubInterval\":[\"200\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0"
        ;;

    "collect_logs")
        logname_prefix=$1;
        aws ssm send-command --document-name "$doc_name" \
            --parameters "{\"Bucket\":[\"emqx-cdk-cluster\"],\"Path\":[\"$cluster\"], \"Prefix\":[\"$logname_prefix\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"emqx\"]}]" \
            --timeout-seconds 600 --max-concurrency "50" --max-errors "0"
        ;;
    *)
        help
        die "unknown command $command"
        ;;
esac
