#!/usr/bin/env bash
set -eu

# load .env if present
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# defaults
PORT="${PORT:-8080}"
ACTIVE_POOL="${ACTIVE_POOL:-blue}"
BLUE_HOST="app_blue"
GREEN_HOST="app_green"

if [ "$ACTIVE_POOL" = "blue" ]; then
  export PRIMARY_HOST="${BLUE_HOST}"
  export SECONDARY_HOST="${GREEN_HOST}"
else
  export PRIMARY_HOST="${GREEN_HOST}"
  export SECONDARY_HOST="${BLUE_HOST}"
fi

mkdir -p nginx

# render template
envsubst '${PRIMARY_HOST} ${SECONDARY_HOST} ${PORT}' < nginx/nginx.conf.template > nginx/default.conf

echo "Rendered nginx/default.conf with PRIMARY=${PRIMARY_HOST}, SECONDARY=${SECONDARY_HOST}, PORT=${PORT}"
echo "Starting docker compose..."
docker compose up -d --remove-orphans

echo "Waiting 1s for nginx to start..."
sleep 1
echo "Done. Nginx on http://localhost:${NGINX_PORT:-8080}"
