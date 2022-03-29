#!/usr/bin/env bash
#
usage() {
    echo "usage: $0 clustername faultname"
    exit 1;
}
set -xe
cluster_name=$1
fault_name=$2
[ -z  "${cluster_name}" ] && usage
[ -z  "${fault_name}" ] && usage
account=$(aws sts get-caller-identity --query "Account" --output text)
region=$(aws configure get region)
taskname="${cluster_name}-chaostest"

taskArn="arn:aws:states:${region}:${account}:stateMachine:${taskname}"

aws stepfunctions start-execution --state-machine-arn "$taskArn" --input "{\"fault_name\": \"$fault_name\"}"
