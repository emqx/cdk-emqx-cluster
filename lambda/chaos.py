#!/usr/bin/env python
import sys
import json
import boto3
import os
import time
import requests
import time
import json
import random

ssm = boto3.client('ssm')
fis = boto3.client('fis')

FAULTS=['emqx-node-shutdown',
        'emqx-high-cpu-100',
        'emqx-high-cpu-80',
        'emqx-high-io-80',
        'emqx-high-io-100',
        'emqx-kill-proc',
        'emqx-high-mem-80',
        'emqx-high-mem-95',
        'emqx-distport-blackhole',
        'emqx-latency-200ms',
        'emqx-packet-loss-10',
        'kafka-plaintext-latency-200',
        'kafka-plaintext-pktloss-10',
        'kafka-plaintext-pktloss-100']

# lambda: Catch and Retry
class Retry(Exception):
    pass
# lambda: Catch but unrecoverable
#
class Fail(Exception):
    pass

def run_cmd_on(cluster_name : str, command_name : str, services : list,
               cmd_parms : dict() = {}):
    '''
    Run system manager command
    '''
    doc_name='-'.join([cluster_name, command_name])
    print(f"run {command_name} ...")
    res = ssm.send_command(DocumentName=doc_name, TimeoutSeconds=30,
                           Targets=[{"Key":"tag:cluster","Values":[cluster_name]},
                                    {"Key":"tag:service","Values":services}],
                           Parameters=cmd_parms
                           )
    """ example of return
    {'Command': {'CommandId': 'bf834b53-0507-4e94-812d-725366985d69',
                 'DocumentName': 'stop_traffic-william-k2',
                 'DocumentVersion': '$DEFAULT',
                 'Comment': '',
                 'ExpiresAfter': datetime.datetime(2022, 2, 16, 15, 19, 22, 524000, tzinfo=tzlocal()),
                 'Parameters': {},
                 'InstanceIds': [],
                 'Targets': [{'Key': 'tag:cluster', 'Values': ['william-k2']}, {'Key': 'tag:service', 'Values': ['loadgen']}],
                 'RequestedDateTime': datetime.datetime(2022, 2, 16, 14, 18, 52, 524000, tzinfo=tzlocal()),
                 'Status': 'Pending', 'StatusDetails': 'Pending',
                 'OutputS3Region': 'eu-west-1', 'OutputS3BucketName': '',
                 'OutputS3KeyPrefix': '', 'MaxConcurrency': '50', 'MaxErrors': '0',
                 'TargetCount': 0, 'CompletedCount': 0, 'ErrorCount': 0, 'DeliveryTimedOutCount': 0,
                 'ServiceRole': '', 'NotificationConfig': {'NotificationArn': '', 'NotificationEvents': [], 'NotificationType': ''},
                 ....
    """
    return res

def find_exp_id(cluster_name : str, fault_name : str, next_token=None) -> str:
    if next_token:
        res=fis.list_experiment_templates(maxResults=100, nextToken=next_token)
    else:
        res=fis.list_experiment_templates(maxResults=100)
    for t in res['experimentTemplates']:
        if t['tags']['cluster'] == cluster_name and t['tags']['fault_name'] == fault_name:
            return t['id']
    if 'nextToken' in res:
        return find_exp_id(cluster_name, fault_name, next_token=res['nextToken'])
    else:
        return ''

def prom_query(url:str, query:str, time: time.time):
    # https://prometheus.io/docs/prometheus/latest/querying/api/
    resp=requests.request(method='POST',url=url, params={'query': query, 'time':time})
    if resp.status_code==200 and resp.json()['status'] == 'success':
        return resp.json()['data']['result']
    else:
        raise Fail(f"prom_query failed with status: {resp.status_code}")

def start_traffic(cluster_name :str, loadgen_args:dict):
    """
    Start traffic with loadgen_args the cluster
    """
    return run_cmd_on(cluster_name, 'start_traffic', ['loadgen'], loadgen_args)

def stop_traffic(cluster_name:str):
    """
    Stop traffic from loadgen in the cluster
    """
    return run_cmd_on(cluster_name, 'stop_traffic', ['loadgen'])


def check_traffic(prom_host:str, time_at:time.time, period:str='5m'):
    url=f"http://{prom_host}/api/v1/query"
    for metric_name in ['emqx_client_subscribe',
                        'emqx_messages_publish',
                        'emqx_client_connected',
                        'emqx_connections_count']:
        # 1) check: all traffic counters are non-zero for last x mins
        print(f"checking {metric_name}")
        query_str="sum(increase(%s[%s]))" % (metric_name, period)
        # example: [{'metric': {}, 'value': [1644946184, '1578.9473684210525']}]
        res=prom_query(url, query_str, time_at)
        if float(res[0]['value'][1]) == 0:
            raise Fail(f"Error: traffic error: {{metric_name}} is 0")

        # 2) check: all emqx nodes get traffic distribution
        query_str="increase(%s[%s])" % (metric_name, period)
        res=prom_query(url, query_str, time_at)
        for r in res:
            ins=(r['metric']['instance'])
            v=r['value'][1]
            if float(v) == 0:
                raise Fail(f"Error: {ins}'s {metric_name} is 0")
    print("Metrics check finished and succeeded")
    return {'result': 'success'}

def inject_fault(cluster_name:str, fault_name:str):
    print(f"inject fault {fault_name}")
    fid = find_exp_id(cluster_name, fault_name)
    if not fid:
        raise Fail(f"Error: inject_fault, fault id not found for {fault_name}")
    res=fis.start_experiment(experimentTemplateId=fid)
    return res

def poll_result(event:dict):
    run = event
    res = True
    # for SSM run commands
    if 'Command' in run:
        cmd=run['Command']
        cmd_id=cmd['CommandId']
        res=ssm.list_command_invocations(CommandId=cmd_id, Details=True)
        if res['CommandInvocations'] == []:
            raise Retry
        for invk in res['CommandInvocations']:
            status = invk['Status']
            if status == 'Success':
                pass
            elif status in ['Pending', 'InProgress', 'Delayed']:
                raise Retry(f"Command { cmd_id } is in status: { status }")
            else:
                raise Fail(f"Command { cmd_id } failed: { status }")
    # for FIS run experiment
    elif 'experiment' in run:
        exp=run['experiment']
        exp_id=exp['id']
        res=fis.get_experiment(id=exp_id)
        status=res['experiment']['state']['status']
        if status == 'completed':
            res={'result': status}
        else:
            raise Retry(f"experiment is in status: {status}")
    else:
        raise Fail('wait_for_finish: unsupported inputs')
    return res


def to_json(d:dict):
    return json.dumps(d, default=str)

def dict_event(evt):
    """
    Ensure the input of lambda is a dict.
    """
    if isinstance(evt , str):
        return json.loads(evt)
    if isinstance(evt, dict):
        return evt
    else:
        raise Fail("unsupported input for lambda: %s", type(evt))

##################################
## Lambda handlers
##  event and context are dict()
##  output must be json
###################################
def random_fault() -> str:
    return random.choice(FAULTS)

def handler_start_traffic(event, context):
    """
    Event Input:
       - traffic_args : str
    Output: Async command call ret for polling
    """
    event = dict_event(event)
    cluster_name=os.environ['cluster_name']
    traffic_args=event['traffic_args']
    lb = '.'.join(['lb', 'int', cluster_name])
    traffic_args['Host']=[lb]
    return to_json(start_traffic(cluster_name, traffic_args))

def handler_stop_traffic(event, context):
    """
    Event Input: -
    Output: Async Command call ret for polling
    """
    event = dict_event(event)
    cluster_name=os.environ['cluster_name']
    return to_json(stop_traffic(cluster_name))

def handler_poll_result(event, context):
    """
    Poll sync call return value, either normal return
    or throw Errors for Retry or Fail
    Event Input:
       - Payload : dict
    Output: -
    """
    event = dict_event(event)
    call_res=json.loads(event['Payload'])
    return to_json(poll_result(call_res))

def handler_check_traffic(event, context):
    """
    Query prometheus and check if the traffic is ok

    Event Input:
       - time : timestamp
       - period: range of time for looking back
             see https://prometheus.io/docs/prometheus/latest/querying/examples/
    Output: -
    """

    event = dict_event(event)
    if 'time' in event:
        time_at=event['time']
    else:
        time_at=time.time()
    period=event['period']
    cluster_name=os.environ['cluster_name']
    prom_host=os.environ.get('prom_host', f"lb.int.{cluster_name}:9090")
    return to_json(check_traffic(prom_host, time_at, period))

def handler_inject_fault(event, context):
    """
    Inject fault to the running cluster

    Event Input:
       - fault_name: Name of the fault in AWS FIS
    Output:
       Async Command call ret for polling
    """
    cluster_name=os.environ['cluster_name']
    fault_name=event['fault_name']
    return to_json(inject_fault(cluster_name, fault_name))


#######################
# For local tests
#######################
def wait_for_finish(run):
    try:
        handler_poll_result({'Payload':run}, {})
    except Retry as e:
        time.sleep(5)
        wait_for_finish(run)


def run_test():
    wait_for_finish(handler_stop_traffic({}, {}))

    traffic_sub_bg={"Host": "dummy", "Command":["sub"],"Prefix":["cdkS1"],"Topic":["root/%c/1/+/abc/#"],"Clients":["200000"],"Interval":["200"]}
    traffic_pub={"Host": "dummy", "Command":["pub"],"Prefix":["cdkP1"],"Topic":["t1"],"Clients":["200000"],"Interval":["200"], "PubInterval":["1000"]}
    traffic_sub={"Host": "dummy", "Command":["sub"],"Prefix":["cdkS2"],"Topic":["t1"],"Clients":["200"],"Interval":["200"]}

    traffics=[traffic_sub_bg, traffic_pub, traffic_sub]

    for t in traffics:
        wait_for_finish(handler_start_traffic({'traffic_args': t}, None))

    # Wait for traffic stable
    time.sleep(300)

    # Check that traffic should be stable
    handler_check_traffic({'time': time.time(), 'period': '5m'}, None)

    # inject fault
    wait_for_finish(handler_inject_fault({'fault_name': random_fault()}, None))

    time.sleep(300)
    # Check that traffic should be stable after fault is gone
    handler_check_traffic({'time': time.time(), 'period': '5m'}, None)

    print("Test is finished")

if __name__ == "__main__":
    """
    For local dev/test
    """
    run_test()
