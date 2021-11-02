#!/usr/bin/env bash
set -euo pipefail

target=${1:-"localhost:13000"}
login="admin:admin"

echo "Setup Data Source..."
curl -X POST ${login}@${target}/api/datasources \
    -H "Accept: application/json" \
    -H 'Content-Type: application/json' \
    --data-binary @- << EOF
{

  "name":"Prometheus",
  "type":"prometheus",
  "url":"http://localhost:9090",
  "access":"proxy",
  "basicAuth":false
}
EOF

echo "Import Dashboards"

for d in 15012 11074;
do
    j=$(curl ${login}@${target}/api/gnet/dashboards/$d | jq .json)
    payload="{\"dashboard\":$j,\"overwrite\":true}"
    curl -X POST ${login}@${target}/api/dashboards/import \
        -H "Accept: application/json" \
        -H "Content-Type: application/json" \
        --data-binary @- << EOF
{
    "dashboard" : $j,
    "overwrite" : true,
	"inputs": [
		{
			"name": "DS_PROMETHEUS",
			"pluginId": "prometheus",
			"type": "datasource",
			"value": "Prometheus"
		}
        ,
		{
			"name": "DS__VICTORIAMETRICS",
			"pluginId": "prometheus",
			"type": "datasource",
			"value": "Prometheus"
		}

	]
}
EOF
done
