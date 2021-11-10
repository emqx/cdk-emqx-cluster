#!/usr/bin/env bash
apt install -y nginx
cat <<EOF > /etc/nginx/nginx.conf
user www-data;
worker_processes auto;
pid /run/nginx.pid;
include /etc/nginx/modules-enabled/*.conf;

worker_rlimit_nofile 1000000;

events {
	worker_connections 1000000;
	# multi_accept on;
}

# emqx
stream {
  upstream stream_backend {
      zone tcp_servers 64000k;
      hash $remote_addr;
      server 127.0.0.1:1883 max_fails=2 fail_timeout=30s;
  }

  server {
      listen 18883 ssl;
      proxy_pass stream_backend;
      proxy_buffer_size 4k;
      ssl_handshake_timeout 15s;
      ssl_certificate     /etc/emqx/certs/cert.pem;
      ssl_certificate_key /etc/emqx/certs/key.pem;
  }
}
EOF

sudo systemctl restart nginx