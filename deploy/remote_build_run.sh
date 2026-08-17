#!/usr/bin/env bash
# Runs ON the EC2 box: unpack, build the image, (re)start the container.
# The host folder ~/runs is mounted to /app/runs so the notebook + git memory
# persist across container restarts and reboots. ~/.env holds OPENAI_API_KEY.
set -euo pipefail

mkdir -p ~/autoresearch ~/runs
tar xzf ~/autoresearch.tgz -C ~/autoresearch
cd ~/autoresearch

docker build -t autoresearch .
docker rm -f autoresearch 2>/dev/null || true

# Env sources, lowest precedence first. ~/.env is the box-local file; the repo's
# own .env (shipped by ship.sh) comes last so it wins on duplicate keys. Either
# may be absent — docker errors on a missing --env-file, so we test each.
ENVFILES=""
[ -f "$HOME/.env" ]             && ENVFILES="$ENVFILES --env-file $HOME/.env"
[ -f "$HOME/autoresearch/.env" ] && ENVFILES="$ENVFILES --env-file $HOME/autoresearch/.env"
[ -z "$ENVFILES" ] && echo "⚠  no .env found (box ~/.env or repo .env) — the loop won't run"

docker run -d --name autoresearch --restart always \
  -p 80:8000 \
  -v ~/runs:/app/runs \
  $ENVFILES \
  autoresearch
docker image prune -f >/dev/null 2>&1 || true
echo "up — http://$(curl -s ifconfig.me)/"
