#!/usr/bin/env bash
# Read-only inventory of the EXISTING cluster. Run in Google Cloud Shell.
set -euo pipefail
PROJECT=parcs-514519
ZONE=us-central1-a
gcloud compute instances list --project "$PROJECT" --filter='name~^parcs-' \
  --format='table(name,zone.basename(),machineType.basename(),status)'
for vm in parcs-master parcs-worker-{1..4}; do
  echo "=== $vm ==="
  gcloud compute instances describe "$vm" --project "$PROJECT" --zone "$ZONE" \
    --format='yaml(name,machineType,cpuPlatform,scheduling,networkInterfaces.networkIP)'
  gcloud compute ssh "$vm" --project "$PROJECT" --zone "$ZONE" \
    --command="sudo docker inspect parcs-node --format '{{.Config.Image}} {{.Image}}'; sudo docker exec parcs-node python -c 'import sys; print(sys.version)'; sudo docker exec parcs-node python -c 'import numpy; print(numpy.__version__)' || true"
done
