#!/usr/bin/env bash
set -euo pipefail

path=/var/lib/grafana/dashboards

curl "https://grafana.com/api/dashboards/1860/revisions/23/download" > "${path}/node_exporter_full.json"
curl "https://grafana.com/api/dashboards/11074/revisions/9/download" > "${path}/node_exporter.json"
curl "https://grafana.com/api/dashboards/15012/revisions/2/download" > "${path}/emqx_exporter.json"
