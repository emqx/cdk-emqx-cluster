#!/usr/bin/env bash
set -euo pipefail

mkdir -p /var/lib/grafana/dashboards
cd /var/lib/grafana/dashboards
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/app_top.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/emqx_exporter.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/node_exporter.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/node_exporter_full.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/proc_top.json"
curl -O "https://raw.githubusercontent.com/k32/grafana-dashboards/master/grafana/dashboards/proc_history.json"
