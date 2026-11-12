#!/bin/bash
set -euxo pipefail

MASTER_IP="$(curl -fsS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/parcs-master-ip')"

# Allow PARCS Master to connect to worker's dynamic ports.
iptables -C INPUT -p tcp -s "${MASTER_IP}/32" \
  --dport 1024:65535 -j ACCEPT 2>/dev/null || \
iptables -I INPUT 1 -p tcp -s "${MASTER_IP}/32" \
  --dport 1024:65535 -j ACCEPT

docker rm -f parcs-node || true

docker run -d \
  --name parcs-node \
  --restart unless-stopped \
  --network host \
  -e "PARCS_ARGS=worker ${MASTER_IP}" \
  docker.io/hummer12007/parcs-node:latest
