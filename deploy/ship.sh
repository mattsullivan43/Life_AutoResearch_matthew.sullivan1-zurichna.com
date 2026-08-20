#!/usr/bin/env bash
# Ship the current code to the EC2 box and (re)deploy. Run from the repo root:
#   EC2_HOST=1.2.3.4 EC2_KEY=~/.ssh/autoresearch.pem ./deploy/ship.sh
# (First time, make sure ~/.env exists on the box — see deploy/DEPLOY_EC2.md.)
set -euo pipefail
HOST="${EC2_HOST:?set EC2_HOST}"
KEY="${EC2_KEY:?set EC2_KEY (path to .pem)}"
USER="${EC2_USER:-ec2-user}"

# package the repo (skip heavy/local stuff; NEVER ship raw broker emails — the
# anonymised extracted/classified JSONs and the runs/ memory DO ship: the demo
# needs the ingested submissions, banked best prompts and notebooks)
# COPYFILE_DISABLE stops macOS tar embedding AppleDouble ._* junk files, which
# land next to real JSONs on the box and crash any *.json directory scan
COPYFILE_DISABLE=1 tar czf /tmp/autoresearch.tgz \
  --exclude .venv --exclude frontend/node_modules --exclude frontend/dist \
  --exclude runs/lab --exclude .git --exclude '*.zip' \
  --exclude '*.eml' --exclude '*.msg' .

SSHOPTS="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

# refuse to deploy while an optimization run is streaming — the container
# restart would kill it mid-flight. Override with FORCE=1.
if [ "${FORCE:-0}" != "1" ]; then
  ACTIVE=$(ssh $SSHOPTS -i "$KEY" "$USER@$HOST" \
    "docker logs autoresearch --since 90s 2>&1 | grep -c 'GET /api/run' || true" 2>/dev/null | tail -1)
  if [ "${ACTIVE:-0}" -gt 0 ] 2>/dev/null; then
    echo "⚠  a run hit /api/run in the last 90s — deploy would kill it. Re-run with FORCE=1 to override."
    exit 1
  fi
fi
scp $SSHOPTS -i "$KEY" /tmp/autoresearch.tgz "$USER@$HOST:~/"
scp $SSHOPTS -i "$KEY" deploy/remote_build_run.sh "$USER@$HOST:~/"
ssh $SSHOPTS -i "$KEY" "$USER@$HOST" "bash ~/remote_build_run.sh"
