# HOWTO CHAOS TEST

## Deploy CDK cluster

example:

Deploy a Cluster named william-k2 
```sh
 CDK_EMQX_CLUSTERNAME=william-k2 cdk deploy --all -c emqx_n=3 -c lg_n=1  -c emqx_ins_type="t3.large" -c loadgen_ins_type="t3.large" -c emqx_src="wget https://www.emqx.com/en/downloads/enterprise/4.4.0/emqx-ee-4.4.0-otp24.1.5-3-ubuntu20.04-amd64.deb" 
```

## Run the test 'emqx-high-mem-80' in cluster 'william-k2'

```sh
bin/trigger_chaos_test.sh william-k2 emqx-high-mem-80
```

