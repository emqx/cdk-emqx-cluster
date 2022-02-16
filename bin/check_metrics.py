#!/usr/bin/env python
#
import sys
from prometheus_api_client import PrometheusConnect
from prometheus_api_client.utils import parse_datetime
from datetime import timedelta
from datetime import datetime

url=sys.argv[1]
time_at=sys.argv[2]
period=sys.argv[3]

prom=PrometheusConnect(url=url, disable_ssl=True)

def error_exit(info:str):
    print(info)
    sys.exit(1)

for metric_name in ['emqx_client_subscribe', 'emqx_messages_publish', 'emqx_client_connected', 'emqx_connections_count']:

    # 1) check: all traffic counters are non-zero for last x mins
    print(f"checking {metric_name}")
    query_str="sum(increase(%s[%s]))" % (metric_name, period)
    # example: [{'metric': {}, 'value': [1644946184, '1578.9473684210525']}]
    res=prom.custom_query(query_str, {'time': time_at})

    if int(res[0]['value'][0]) == 0:
        error_exit("Error: traffic error: {{metric_name}} is 0")

    # 2) check: all emqx nodes get traffic distribution
    query_str="increase(%s[%s])" % (metric_name, period)
    res=prom.custom_query(query_str, {'time': time_at})
    for r in res:
        ins=(r['metric']['instance'])
        v=r['value'][1]
        if v == 0:
            error_exit(f"Error: {ins}'s {metric_name} is 0")

print("Metrics check finished and succeeded")
