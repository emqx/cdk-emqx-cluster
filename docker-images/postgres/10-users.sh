#!/bin/bash
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    create user system_monitor with password 'system_monitor_password';
    create user grafana with password 'grafana';
EOSQL
