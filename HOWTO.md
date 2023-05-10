# Prepare

## Clone this repo and cd to project root
```bash
git clone git@github.com:emqx/cdk-emqx-cluster.git
cd cdk-emqx-cluster
```
## Decide cluster context parameters

All Supported configs are listed here:

All configs are optional, specify with `cdk deploy -c k1=v1 -c k2=v2`

```bash
# EMQX instance TYPE
# default: t3a.small
emqx_ins_type


# EMQX instance type for Core nodes (RLOG DB backend)
# default: same as emqx_ins_type
emqx_core_ins_type


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

# External resource instance TYPE
# Nodes for external resources are just created and not used by the cluster.
# They may be used to provision external resources like Redis, Postgres, etc.
# default: t3a.small
ext_ins_type

# Number of nodes for external resources.
# default: 0
ext_n

# Extra EBS vol size (in GB) for EMQX DATA per EMQX Instance
# default: null
emqx_ebs

# Kafka Volume size (in GB), set a vaule to enable kafka in AWS MSK
# via bootstrap brokers:
#   TLS: 9094
# default: null, (no kafka)
kafka_ebs

# Specify how to fetch emqx package by
#
# - Download deb file from web
#   emqx_src="wget https://www.emqx.io/downloads/broker/v4.3.0/emqx-ubuntu20.04-4.3.0-amd64.deb"
# - Fetch deb file from S3. Note, emqx node only has access to cluster bucket: s3://emqx-cdk-cluster/${cluster_name}
#   emqx_src="aws s3 cp s3://emqx-cdk-cluster/william-k2/emqx-5.0.0-beta.3-7f31cd08-otp24.2.1-ubuntu20.04-amd64.deb ./"
# - build from src
#   emqx_src="git clone -b some_branch https://github.com/emqx/emqx"
#
# default: "git clone https://github.com/emqx/emqx"
emqx_src

# Retain shared data EFS after cluster destroy
# Set it to 'False' to create new tmp EFS that will be removed together with the cluster
# Set it to 'True' to create new and the EFS will be preserved after cluster destroy.
# Set it to FIS id (like 'fs-0c86dd7fcd8ca836c') to reuse the Existing EFS without create new one.
# default: False
retain_efs

# Docker image that'll be used to build EMQ X
# default: ghcr.io/emqx/emqx-builder/5.0-17:1.13.4-24.2.1-1-ubuntu20.04
emqx_builder_image

# Monitoring Postgres password
# Set the password for the Postgres instance that is used by system_monitor
# If unset, a random one will be generated.
# If using a retained EFS, you should take note of the generated password
# because it'll be persisted between clusters.
emqx_monitoring_postgres_password

# Enable Nginx
# Nginx is used for SSL termination for EMQ X.  But it spawns
# one worker process per machine core, so for large machines
# like `c6g.metal` it may take 19.2 % of the memory at rest.
# default: True
emqx_enable_nginx

# EMQ X Build Profile
# Which profile to build EMQ X with, as in "make $PROFILE".
# To build with Elixir, use "emqx-elixirpkg".
# default: emqx-pkg
emqx_build_profile

# Enable Pulsar
# Whether to deploy Pulsar.  Requires to be deployed over at least 2 AZs.
# Will have TLS enabled.
# default: False
emqx_pulsar_enable

# Enable Postgres
# Whether to deploy Postgres.
# default: True
emqx_postgres_enable

```

## Make sure you have AWS credentials in ~/.aws/

## hotpot team, ensure you are using eu-west-1
``` bash
(.venv) bash-5.1# cat ~/.aws/config
[default]
region = eu-west-1
output = json
```

## Run cdk in docker

execute `./run` to run cdk inside the container with args passed to it.
e.g.

```bash
env CDK_EMQX_CLUSTERNAME=william ./run cdk synth CdkEmqxClusterStack
```

To have Docker debug output, use `DEBUG=1`:

```bash
env DEBUG=1 ./run cdk synth CdkEmqxClusterStack
```

If you want to enter bash inside the container for debugging purposes, just use:

```bash
./run bash
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
ssh emqx-0
# LOADGEN
ssh loadgen-0
# ETCD
ssh etcd0
```

# Provision Grafana Dashboards

```
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
CDK_EMQX_CLUSTERNAME=william cdk deploy --all -c emqx_src="git clone -b YOUR_BRANCH https://github.com/emqx/emqx" -c emqx_n=2 -c emqx_ins_type="m5.2xlarge" -c loadgen_ins_type="m5n.xlarge" -c emqx_ebs=20
```
The `emqx_ebs` is needed since these instances do not have storage by default.


## Kafka data bridge test with emqx enterprise

```bash
CDK_EMQX_CLUSTERNAME=william-k2 cdk deploy --all  -c emqx_n=1 -c lg_n=2 -c emqx_ins_type="m5.4xlarge" -c loadgen_ins_type="m5n.4xlarge" -c emqx_src="wget https://www.emqx.com/en/downloads/enterprise/4.3.5/emqx-ee-ubuntu20.04-4.3.5-amd64.deb" -c kafka_ebs=20 -c retain_efs='fs-0bbcde0cf702b4ccb' -c emqx_monitoring_postgres_password=cdniylye --parameters sshkey=qzhuyan
```

## Pulsar data bridge test with emqx enterprise

CDK will print both the URL to be used for connecting to Pulsar:

```
# example
CdkEmqxClusterStack.PulsarProxyURL = pulsar+ssl://ad72a1f2bc1514e43816a5a87ef5ad56-680660445.sa-east-1.elb.amazonaws.com:6651
# command to run in bastion and get the url
CdkEmqxClusterStack.PulsarProxyURLcommandruninbastion = kubectl -n pulsar get svc thales-pulsar-release-proxy -o=jsonpath="{.status.loadBalancer.ingress[0].hostname}"
```

```sh
  time cdk deploy CdkEmqxClusterStack \
       -c emqx_n=1 \
       -c emqx_num_core_nodes=1 \
       -c emqx_db_backend="rlog" \
       -c lg_n=0 \
       -c emqx_enable_nginx=False \
       -c emqx_pulsar_enable=True \
       `#-c retain_efs=True` \
       -c emqx_monitoring_postgres_password="mypass" \
       -c emqx_src="wget https://www.emqx.com/en/downloads/enterprise/4.4.5/emqx-ee-4.4.5-otp24.1.5-3-ubuntu20.04-amd64.deb" \
       `#-c emqx_builder_image="ghcr.io/emqx/emqx-builder/5.0-17:1.13.4-24.2.1-1-ubuntu20.04"` \
       `#-c emqx_build_profile="emqx-elixir-pkg"` \
       -c emqx_ins_type="t3a.small" \
       -c emqx_core_ins_type="t3a.small" \
       -c loadgen_ins_type="t3a.small"
```

## MAX connections test with AWS bare metal

Following setup could reach 5.5M connections per instance.

```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy CdkEmqxClusterStack -c retain_efs='fs-0c86dd7fcd8ca836c'  -c emqx_n=1 -c lg_n=2 -c emqx_ins_type="c6g.metal" -c loadgen_ins_type="c6g.metal"

```

# Bootstrapping a new region

When deploying to a new region, run `cdk boostrap`.

Note: this requires the executing user to have `ecr:CreateRepository` permissions in the region.

Also, make sure there is a key pair you have access to in your new region.

You could create the key pair via:

```sh
aws ec2 create-key-pair \
      --key-name "mykey_${USER}" \
      --key-type rsa \
      --key-format pem \
      --query "KeyMaterial" \
      --output text > ~/.ssh/id_rsa.emqx.sa-east
```

OR append following override in cdk cli to use existing key.

```sh
--parameters sshkey="mykey_${USER}"
```

# Troubleshooting

## Monitoring Cluster hangs deployment

If your deploy hangs forever waiting for the ECS Monitoring Cluster to
be ready, and you are using an existing EFS ID (with Postgres data),
then probably the previous Postgres didn't shutdown properly and you
need to reset its WAL (write ahead log).

A quick and dirty way to do it:

### Set the service desired count to 0

Change `$YOUR_CDK_CLUSTER_NAME` to the appropriate value.

```sh
 (
    set -x

    AWS_CLUSTER_NAME=$(
      aws ecs list-clusters \
      | jq -r '.clusterArns[]' \
      | grep $YOUR_CDK_CLUSTER_NAME \
      | cut -d"/" -f2)
    AWS_SERVICE_NAME=$(
      aws ecs list-services --cluster ${AWS_CLUSTER_NAME} \
        | jq -r '.serviceArns[]' \
        | cut -d"/" -f3 )
    aws ecs update-service \
        --cluster ${AWS_CLUSTER_NAME} \
        --service ${AWS_SERVICE_NAME} \
        --desired-count 0
  )
```

This should make the deploy finalize.

### Manually fix the WAL from the Bastion

Use the SSH command from CDK to log into the Bastion machine and then
install Docker.

```sh
sudo yum -y install docker
sudo systemctl start docker
sudo docker run --rm -it -v /mnt/efs-data/pgsql_data/:/external/ ghcr.io/iequ1/sysmon-postgres:1.3.1 bash
```

Inside Docker:

```sh
su postgres
cd /external
pg_resetwal -f /external
```

Exit Docker.

### Restart monitoring cluster

Change `$YOUR_CDK_CLUSTER_NAME` to the appropriate value.

```sh
 (
    set -x

    AWS_CLUSTER_NAME=$(
      aws ecs list-clusters \
      | jq -r '.clusterArns[]' \
      | grep $YOUR_CDK_CLUSTER_NAME \
      | cut -d"/" -f2)
    AWS_SERVICE_NAME=$(
      aws ecs list-services --cluster ${AWS_CLUSTER_NAME} \
        | jq -r '.serviceArns[]' \
        | cut -d"/" -f3 )
    aws ecs update-service \
        --cluster ${AWS_CLUSTER_NAME} \
        --service ${AWS_SERVICE_NAME} \
        --desired-count 1
  )
```
