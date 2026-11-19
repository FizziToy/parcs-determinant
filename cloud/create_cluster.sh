#!/usr/bin/env bash
# Run FROM THE PROJECT ROOT in GCP Cloud Shell. Inspect billable resources first.
set -euo pipefail
PROJECT="$(gcloud config get-value project 2>/dev/null)"
if [[ -z "$PROJECT" || "$PROJECT" == '(unset)' ]]; then
  echo 'Select a GCP project first: gcloud config set project YOUR_PROJECT_ID' >&2; exit 1
fi
ZONE="${ZONE:-us-central1-a}"
MACHINE="${MACHINE:-e2-small}"
WORKER_COUNT="${WORKER_COUNT:-1}"
if ! [[ "$WORKER_COUNT" =~ ^[1-4]$ ]]; then
  echo "WORKER_COUNT must be 1, 2, 3 or 4" >&2; exit 1
fi
if [[ ! -f cloud/master-startup.sh ]]; then
  echo 'Run this script from the parcs-determinant project directory.' >&2; exit 1
fi
echo "Project=$PROJECT Zone=$ZONE Machine=$MACHINE"
echo "Creating master + $WORKER_COUNT worker VM(s), potentially BILLABLE outside free trial."
echo 'You can delete all using: bash cloud/delete_cluster.sh'
gcloud services enable compute.googleapis.com
if ! gcloud compute firewall-rules describe parcs-internal --project "$PROJECT" >/dev/null 2>&1; then
  # Only other VMs with the parcs-node network tag can reach these ports.
  gcloud compute firewall-rules create parcs-internal \
    --network=default --direction=INGRESS --priority=1000 \
    --action=ALLOW --rules=tcp:8080,tcp:1024-65535 \
    --source-tags=parcs-node --target-tags=parcs-node
fi
if ! gcloud compute instances describe parcs-master --zone "$ZONE" >/dev/null 2>&1; then
  gcloud compute instances create parcs-master --zone "$ZONE" \
    --machine-type "$MACHINE" --image-family cos-stable --image-project cos-cloud \
    --boot-disk-size=20GB --boot-disk-type=pd-standard --tags=parcs-node \
    --metadata-from-file startup-script=cloud/master-startup.sh
fi
MASTER_IP="$(gcloud compute instances describe parcs-master --zone "$ZONE" \
  --format='get(networkInterfaces[0].networkIP)')"
echo "Master internal IP: ${MASTER_IP}"
for i in $(seq 1 "$WORKER_COUNT"); do
  if ! gcloud compute instances describe "parcs-worker-$i" --zone "$ZONE" >/dev/null 2>&1; then
    gcloud compute instances create "parcs-worker-$i" --zone "$ZONE" \
      --machine-type "$MACHINE" --image-family cos-stable --image-project cos-cloud \
      --boot-disk-size=20GB --boot-disk-type=pd-standard --tags=parcs-node \
      --metadata="parcs-master-ip=${MASTER_IP}" \
      --metadata-from-file startup-script=cloud/worker-startup.sh
  fi
done
gcloud compute instances list --filter='name~^parcs-'
echo 'Verify startup logs via: gcloud compute ssh parcs-master --zone '"$ZONE"' --command="sudo docker ps"'
echo 'Cloud Shell tunnel (leave it running): gcloud compute ssh parcs-master --zone '"$ZONE"' -- -N -L 8080:127.0.0.1:8080'
echo 'Then use Cloud Shell Web preview -> Preview on port 8080.'
