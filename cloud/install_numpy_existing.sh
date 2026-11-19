#!/usr/bin/env bash
# OPTIONAL dependency installation on Workers, after inventory confirms Python 2.7.
# The stock PARCS Dockerfile uses Python 2; do not change/recreate VMs here.
set -euo pipefail
for vm in parcs-worker-{1..4}; do
  echo "Installing/checking NumPy in $vm"
  gcloud compute ssh "$vm" --project parcs-514519 --zone us-central1-a \
    --command="set -e; sudo docker exec parcs-node python -c 'import sys; assert sys.version_info[:2] == (2, 7), sys.version'; sudo docker exec parcs-node python -m pip install --only-binary=:all: numpy==1.16.6; sudo docker exec parcs-node python -c 'import numpy; print(numpy.__version__)'"
done
