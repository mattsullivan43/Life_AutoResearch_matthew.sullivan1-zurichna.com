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
docker run -d --name autoresearch --restart always \
  -p 80:8000 \
  -v ~/runs:/app/runs \
  --env-file ~/.env \
  autoresearch
docker image prune -f >/dev/null 2>&1 || true
echo "up — http://$(curl -s ifconfig.me)/"
