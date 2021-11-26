#!/usr/bin/env bash
set -euo pipefail
target=${1:-"localhost:19090"}
curl -XPOST http://"$target"/api/v1/admin/tsdb/snapshot