#!/bin/bash

###############################################################################
# Fault injection experiments
# For supported faults see chaos_test.py
#
###############################################################################

# cluster name 'CDK_EMQX_CLUSTERNAME' when you deploy cdk
cluster=$1

#
fault=$2

die() {
    echo $1
    exit 1;
}

# experiment
expid=$(aws fis list-experiment-templates | jq -r --arg cluster "$cluster" --arg name "$fault" '.experimentTemplates[] |
    select(getpath(["tags","cluster"]) == $cluster and getpath(["tags","fault_name"]) == $name) | .id')

if [ -z "$expid" ]; then
    die "experiment not found";
fi

aws fis start-experiment --experiment-template-id="$expid"
