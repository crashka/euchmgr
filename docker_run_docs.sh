#!/usr/bin/env bash

set -x

admin_url="{url: 'docs/admin_api.yaml', name: 'Admin API'}"
mobile_url="{url: 'docs/mobile_api.yaml', name: 'Mobile API'}"

docker run --name swagger-ui -d -p 8080:8080 \
       -v /var/docker/docs:/usr/share/nginx/html/docs \
       -e URLS="[${admin_url}, ${mobile_url}]" \
       docker.swagger.io/swaggerapi/swagger-ui
