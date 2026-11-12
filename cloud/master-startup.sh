#!/bin/bash
set -euxo pipefail
# Container-Optimized OS has Docker preinstalled. Host networking is important.
docker rm -f parcs-node || true
docker run -d --name parcs-node --restart unless-stopped --network host \
  -e PARCS_ARGS='master' docker.io/hummer12007/parcs-node:latest
