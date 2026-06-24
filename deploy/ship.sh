#!/usr/bin/env bash
# Ship the current code to the EC2 box and (re)deploy. Run from the repo root:
#   EC2_HOST=1.2.3.4 EC2_KEY=~/.ssh/autoresearch.pem ./deploy/ship.sh
# (First time, make sure ~/.env exists on the box — see deploy/DEPLOY_EC2.md.)
set -euo pipefail
HOST="${EC2_HOST:?set EC2_HOST}"
KEY="${EC2_KEY:?set EC2_KEY (path to .pem)}"
USER="${EC2_USER:-ec2-user}"

# package the repo (skip heavy/local/secret stuff)
tar czf /tmp/autoresearch.tgz \
  --exclude .venv --exclude frontend/node_modules --exclude frontend/dist \
  --exclude runs --exclude .git --exclude '*.zip' .

SSHOPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"
scp $SSHOPTS -i "$KEY" /tmp/autoresearch.tgz "$USER@$HOST:~/"
scp $SSHOPTS -i "$KEY" deploy/remote_build_run.sh "$USER@$HOST:~/"
ssh $SSHOPTS -i "$KEY" "$USER@$HOST" "bash ~/remote_build_run.sh"
