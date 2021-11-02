# Prepare

## Clone this repo and cd to project root
```bash
git clone git@github.com:qzhuyan/cdk-emqx-cluster.git
cd cdk-emqx-cluster
```
## Modify the number of nodes and instance size in
```
In cdk_emqx_cluster/cdk_emqx_cluster_stack.py

emqx_ins_type = 't3a.small'
numEmqx=2
emqx_ebs_vol_size=8
loadgen_ins_type = 't3a.micro'
numLg=1
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

## In docker prepare python venv

```bash
npm install -g aws-cdk
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt

```

Or you just run `./bin/start.sh`

# Deploy
## Dry run create cluster named william

```bash
CDK_EMQX_CLUSTERNAME=william cdk synth
```

## Real run
```bash
CDK_EMQX_CLUSTERNAME=william cdk deploy
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

Fist ssh to loadgen

``` bash
# become root
sudo bash

# goto /root/emqtt-bench

cd /root/emqtt-bench

epmd -daemon; ./emqtt_bench conn -h lb.int.william

```

# Destroy cluster
```
CDK_EMQX_CLUSTERNAME=william cdk destroy

```
