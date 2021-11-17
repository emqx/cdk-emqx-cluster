#!/bin/bash

################################################################################
# This script is used to send a command to the device with AWS SSM
################################################################################


# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
cluster=$1

# CdkChaosTests.ControlCmd,
# scripts are under cdk_emqx_cluster/ssm_docs/
command=$2

die() {
    echo $1
    exit 1;
}

if [ -z "$cluster" ]; then
    die "cluster not set";
fi

doc_name=$(aws ssm list-documents --filters "Key=tag:cluster,Values=$cluster" --filters "Key=tag:cmd,Values=$command" | jq -r '.DocumentIdentifiers[0].Name')
if [[ "$doc_name" == "null" || ! $? ]]; then
    die "command '$command' not found, did you deploy the CdkChaosTests Stack?"
fi

case $command in
    "start_traffic")
        # supply command parameters and targets
        LB="lb.int.$cluster"
        aws ssm send-command --document-name "$doc_name" --document-version "1" \
            --parameters "{\"Host\": [\"$LB\"], \"Command\":[\"sub\"],\"Prefix\":[\"cdk\"],\"Topic\":[\"topic_a\"],\"Clients\":[\"200\"],\"Interval\":[\"10\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0"

        aws ssm send-command --document-name "$doc_name" --document-version "1" \
            --parameters "{\"Host\": [\"$LB\"], \"Command\":[\"pub\"],\"Prefix\":[\"cdk\"],\"Topic\":[\"topic_a\"],\"Clients\":[\"200\"],\"Interval\":[\"10\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"loadgen\"]}]" \
            --timeout-seconds 60 --max-concurrency "30" --max-errors "0"
        ;;
    "collect_logs")
        aws ssm send-command --document-name "$doc_name" --document-version "1" \
            --parameters "{\"Bucket\":[\"emqx-cdk-cluster\"],\"Path\":[\"$cluster\"]}" \
            --targets "[{\"Key\":\"tag:cluster\",\"Values\":[\"$cluster\"]},{\"Key\":\"tag:service\",\"Values\":[\"emqx\"]}]" \
            --timeout-seconds 600 --max-concurrency "50" --max-errors "0" --region eu-west-1
        ;;
    *)
        die "unknown command $command"
        ;;
esac