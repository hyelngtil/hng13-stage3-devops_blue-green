#!/usr/bin/env bash
set -eu
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
else
  echo ".env missing"; exit 1
fi

if [ "$ACTIVE_POOL" = "blue" ]; then
  NEW=green
else
  NEW=blue
fi

perl -pi -e "s/^ACTIVE_POOL=.*/ACTIVE_POOL=${NEW}/" .env
export ACTIVE_POOL=${NEW}

if [ "$ACTIVE_POOL" = "blue" ]; then
  export PRIMARY_HOST=app_blue; export SECONDARY_HOST=app_green
else
  export PRIMARY_HOST=app_green; export SECONDARY_HOST=app_blue
fi

envsubst '${PRIMARY_HOST} ${SECONDARY_HOST} ${PORT}' < nginx/nginx.conf.template > nginx/default.conf

docker exec nginx nginx -s reload

echo "Switched ACTIVE_POOL -> ${NEW} and reloaded nginx"
