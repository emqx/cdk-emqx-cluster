#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/grafana/dashboards
cd /var/lib/grafana/dashboards
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/app_top.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/emqx_exporter.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/node_exporter.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/node_exporter_full.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/proc_top.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/proc_history.json"
