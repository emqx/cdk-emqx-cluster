FROM grafana/grafana:latest

COPY datasources.yml  /etc/grafana/provisioning/datasources/
COPY dashboards/*.yml /etc/grafana/provisioning/dashboards/
COPY grafana_setup.sh /opt/grafana_setup.sh

USER root
RUN apk add curl
RUN /opt/grafana_setup.sh

USER grafana
