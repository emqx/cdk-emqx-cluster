# Prepare

## Clone this repo and cd to project root
```bash
git clone git@github.com:qzhuyan/cdk-emqx-cluster.git
cd cdk-emqx-cluster
```
## Decide cluster context parameters

All Supported configs are listed here:

All configs are optional, specify with `cdk deploy -c k1=v1 -c k2=v2`

```bash
# EMQX instance TYPE
# default: t3a.small
emqx_ins_type


# Number of EMQXs
# default: 2
emqx_n

# Type of DB Backend
# choice: "mnesia" | "rlog"
# default: "mnesia"
emqx_db_backend

# Number of core nodes. Only relevant if `emqx_db_backend' = "rlog"
# default: same as `emqx_n'
emqx_num_core_nodes

# Loadgen instance type
# default: # default: t3a.small
loadgen_ins_type

# Number of Loadgens
# default: 1
lg_n

# Extra EBS vol size (in GB) for EMQX DATA per EMQX Instance
# default: null
emqx_ebs

# Kafka Volume size (in GB), set a vaule to enable kafka in AWS MSK
# via bootstrap brokers:
#   TLS: 9094
# default: null, (no kafka)
kafka_ebs

# Specify how to fetch emqx package
# either by downloading deb
# emqx_src="wget https://www.emqx.io/downloads/broker/v4.3.0/emqx-ubuntu20.04-4.3.0-amd64.deb"
# OR
# build from src
# emqx_src="git clone -b some_branch https://github.com/emqx/emqx"
# default: "git clone https://github.com/emqx/emqx"
emqx_src

# Retain shared data EFS after cluster destroy
# Set it to 'False' to create new tmp EFS that will be removed together with the cluster
# Set it to 'True' to create new and the EFS will be preserved after cluster destroy.
# Set it to FIS id (like 'fs-0c86dd7fcd8ca836c') to reuse the Existing EFS without create new one.
# default: False
retain_efs

```

## Make sure you have AWS credentials in ~/.aws/

## hotpot team, ensure you are using eu-west-1
``` bash
(.venv) bash-5.1# cat ~/.aws/config
[default]
region = eu-west-1
output = json
```

## Start cdk docker container

``` bash
docker run --rm -it -v ~/.aws:/root/.aws -v $(pwd):/opt/app contino/aws-cdk bash

```

## Run cdk in docker

execute `./run` with all the cdk args passed to it.
e.g.

```bash
./run synth CdkEmqxClusterStack
```

# Deploy
## Dry run create cluster named william

```bash
CDK_EMQX_CLUSTERNAME=william cdk synth CdkEmqxClusterStack
```

## Only deploy cluster
```bash
CDK_EMQX_CLUSTERNAME=william cdk synth CdkEmqxClusterStack
```

## Real run
```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy CdkEmqxClusterStack
```

## Lazy Note: If you want to deploy EMQX with private branch, with 5 emqx nodes
```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy CdkEmqxClusterStack -c emqx_src="git clone -b your_branch https://github.com/emqx/emqx" -c emqx_n=5
```

At the end of run, you will get some outputs such like,

```bash
Outputs:
CdkEmqxClusterStack.BastionBastionHostId8F8CEB82 = i-00e761468efeebeaf
CdkEmqxClusterStack.ClusterName = william
CdkEmqxClusterStack.Hostsare = emqx-0.int.william
emqx-1.int.william
etcd0.int.william
etcd1.int.william
etcd2.int.william
loadgen-0.int.william
CdkEmqxClusterStack.Loadbalancer = emqx-nlb-william-dd3bcdae49c13be7.elb.eu-west-1.amazonaws.com
CdkEmqxClusterStack.MonitoringGrafana = lb.int.william:3000
CdkEmqxClusterStack.MonitoringPrometheus = lb.int.william:9090
CdkEmqxClusterStack.SSHCommandsforAccess = ssh -A -l ec2-user 54.247.190.179 -L8888:emqx-nlb-william-bbbbbbb.elb.eu-west-1.amazonaws.com:80 -L 9999:lb.int.william:80 -L 13000:lb.int.william:3000
CdkEmqxClusterStack.SSHEntrypoint = 54.247.190.179
```
It shows you the information of the cluster

1. ClusterName: william
1. EC2 Hosts:
  emqx-0.int.william
  emqx-1.int.william
  etcd0.int.william
  etcd1.int.william
  etcd2.int.william
  loadgen-0.int.william
1. loadbalancer dns name:
  emqx-nlb-william-dd3bcdae49c13be7.elb.eu-west-1.amazonaws.com

1. Grafana Monitoring
  lb.int.william:3000

1. Lazy command access the cluster with ssh proxy
   where emqx WEBUI is on localhost:8888, grafana dashboard is on localhost:13000
```bash
ssh -A -l ec2-user 54.247.190.179 -L8888:emqx-nlb-william-bbbbbbb.elb.eu-west-1.amazonaws.com:80 -L 9999:lb.int.william:80 -L 13000:lb.int.william:3000
```

## Access the cluster via Bastion
```bash
# ensure ssh-agent is running if not
eval `ssh-agent`

# add ssh key
ssh-add ~/.ssh/key_for_your_cluster.pem
```

```bash
ssh -A -l ec2-user 54.247.190.179 -L8888:emqx-nlb-william-bbbbbbb.elb.eu-west-1.amazonaws.com:80 -L 9999:lb.int.william:80 -L 13000:lb.int.william:3000
```
## From Bastion you can ssh to the other EC2 instances

``` bash
# EMQX
ssh -l ubuntu emqx-0.int.william
# LOADGEN
ssh -l ubuntu loadgen-0.int.william
# ETCD
ssh -l ubuntu etcd0.int.william
```

# Provision Grafana Dashboards

```bash
# In this project root
~/./bin/grafana_setup.sh

# Monitoring

Open web browser and access the grafana via localhost:13000

username: admin
password: admin
```

# Use Loadgen

First ssh to loadgen

``` bash
# become root
sudo bash

# goto /root/emqtt-bench

cd /root/emqtt-bench

./emqtt_bench conn -h lb.int.william

```

# Destroy cluster
```
CDK_EMQX_CLUSTERNAME=william cdk destroy CdkEmqxClusterStack

```

# Performance tests

## Persistent session test
*NOTE:* These are pretty large instances, so only use this for finding performance numbers.

For some more relevant performance tests, you can use larger instances. For a two node emqx cluster with one loadgen with a particular branch:
```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy --all -c emqx_src="git clone -b YOUR_BRANCH https://github.com/emqx/emqx" -c emqx_n=2 -c emqx_ins_type="m5.2xlarge" -c loadgen_ins_type="m5n.xlarge" -c emqx_eb=20 -c keep_efs=True
```
The `emqx_ebs` is needed since these instances do not have storage by default.


## Kafka data bridge test with emqx enterprise

```bash
CDK_EMQX_CLUSTERNAME=william-kafka cdk deploy --all  -c emqx_n=1 -c lg_n=2  -c emqx_ins_type="m5.4xlarge" -c loadgen_ins_type="m5n.4xlarge"  -c emqx_src="wget https://www.emqx.com/en/downloads/enterprise/4.3.5/emqx-ee-ubuntu20.04-4.3.5-amd64.deb" -c kafka_ebs=10
```

## MAX connections test with AWS bare metal

Following setup could reach 5.5M connections per instance.

```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy CdkEmqxClusterStack -c retain_efs='fs-0c86dd7fcd8ca836c'  -c emqx_n=1 -c lg_n=2 -c emqx_ins_type="c6g.metal" -c loadgen_ins_type="c6g.metal"

```
