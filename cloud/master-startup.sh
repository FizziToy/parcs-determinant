#!/bin/bash
set -euxo pipefail
# Allow PARCS workers to register with the master.
iptables -C INPUT -p tcp -s 10.128.0.0/24 --dport 8080 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p tcp -s 10.128.0.0/24 --dport 8080 -j ACCEPT
# Container-Optimized OS has Docker preinstalled. Host networking is important.
docker rm -f parcs-node || true
docker run -d --name parcs-node --restart unless-stopped --network host \
  -e PARCS_ARGS='master' docker.io/hummer12007/parcs-node:latest
