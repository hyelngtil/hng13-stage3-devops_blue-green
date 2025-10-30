#!/usr/bin/env bash
set -eu

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

NGINX=http://localhost:${NGINX_PORT:-8080}
BLUE=http://localhost:${BLUE_HOST_PORT:-8081}
GREEN=http://localhost:${GREEN_HOST_PORT:-8082}

echo "Baseline: GET /version via nginx"
curl -s -D - $NGINX/version -o /tmp/version_out || true
sed -n '1,40p' /tmp/version_out || true

echo
echo "Triggering chaos on blue: POST $BLUE/chaos/start?mode=error"
curl -s -X POST "$BLUE/chaos/start?mode=error" || true
sleep 1

echo "Now rapidly requesting $NGINX/version 20 times and printing app headers"
for i in $(seq 1 20); do
  echo -n "$i: "
  curl -s -D - $NGINX/version -o /dev/null | egrep -i "HTTP/|X-App-Pool|X-Release-Id" | tr '\n' ' ' ; echo
  sleep 0.2
done

echo "Stopping chaos on blue"
curl -s -X POST "$BLUE/chaos/stop" || true
echo "Done!"