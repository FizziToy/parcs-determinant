#!/usr/bin/env bash
set -euo pipefail
ZONE="${ZONE:-us-central1-a}"
for vm in parcs-master parcs-worker-1 parcs-worker-2 parcs-worker-3 parcs-worker-4; do
  if gcloud compute instances describe "$vm" --zone "$ZONE" >/dev/null 2>&1; then
    gcloud compute instances delete "$vm" --zone "$ZONE" --quiet
  fi
done
if gcloud compute firewall-rules describe parcs-internal >/dev/null 2>&1; then
  gcloud compute firewall-rules delete parcs-internal --quiet
fi
