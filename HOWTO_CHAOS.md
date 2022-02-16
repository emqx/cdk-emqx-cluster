# HOWTO CHAOS TEST

## Deploy CDK cluster

example:

Deplay a Cluster named william-k2 
```sh
 CDK_EMQX_CLUSTERNAME=william-k2 cdk deploy --all -c emqx_n=3 -c lg_n=1  -c emqx_ins_type="t3.large" -c loadgen_ins_type="t3.large"  -c emqx_src="wget https://www.emqx.com/en/downloads/enterprise/4.4.0/emqx-ee-4.4.0-otp24.1.5-3-ubuntu20.04-amd64.deb" 
```

Take notes for the ssh tunnel from output 
```
CdkEmqxClusterStack.SSHCommandsforAccess = ssh -A -l ec2-user 123.249.237.181 -L 8888:lb.int.william-k2:80 -L 13000:lb.int.william-k2:3000 -L 19090:lb.int.william-k2:9090
```

## In another shell, open ssh tunnel with the note taken above 

```
ssh -A -l ec2-user 123.249.237.181 -L 8888:lb.int.william-k2:80 -L 13000:lb.int.william-k2:3000 -L 19090:lb.int.william-k2:9090
```

## Run all the tests:

```sh
bin/chaos_test.sh william-k2 all
```

## Or you can run one test with testcase name

```sh
bin/chaos_test.sh william-k2 emqx-high-cpu-80
```

## Check available tests

Check available tests in the cluster

```sh
bin/chaos_test.sh william-k2 list
```

