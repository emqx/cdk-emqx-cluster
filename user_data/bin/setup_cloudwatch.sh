#!/usr/bin/env sh

cloudwatch() {
    case "$(uname -m)" in
        x86_64)
            arch=amd64
            ;;
        aarch64)
            arch=arm64
            ;;
    esac

    wget "https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/${arch}/latest/amazon-cloudwatch-agent.deb"
    dpkg -i -E ./amazon-cloudwatch-agent.deb

    cat <<EOF > /opt/aws/amazon-cloudwatch-agent/bin/config.json
{
  "agent": {
    "metrics_collection_interval": 60,
    "run_as_user": "root"
  },
  "metrics": {
    "aggregation_dimensions": [
      ["InstanceId"]
    ],
    "append_dimensions": {
      "AutoScalingGroupName": "\${aws:AutoScalingGroupName}",
      "ImageId": "\${aws:ImageId}",
      "InstanceId": "\${aws:InstanceId}",
      "InstanceType": "\${aws:InstanceType}"
    },
    "metrics_collected": {
      "disk": {
        "measurement": ["used_percent"],
        "metrics_collection_interval": 60,
        "resources": ["*"]
      },
      "prometheus": {
        "log_group_name" : "emqx-metrics",
        "prometheus_config_path" : "/opt/aws/amazon-cloudwatch-agent/var/prometheus.yaml",
         "measurement": [],
        "emf_processor": {
          "metric_declaration_dedup": true,
          "metric_namespace": "PrometheusTest",
          "metric_unit":{
            "jvm_threads_current": "Count",
            "jvm_classes_loaded": "Count",
            "java_lang_operatingsystem_freephysicalmemorysize": "Bytes",
            "catalina_manager_activesessions": "Count",
            "jvm_gc_collection_seconds_sum": "Seconds",
            "catalina_globalrequestprocessor_bytesreceived": "Bytes",
            "jvm_memory_bytes_used": "Bytes",
            "jvm_memory_pool_bytes_used": "Bytes"
          },
      }
    }
  }
}
EOF
    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/bin/config.json
}

cloudwatch
