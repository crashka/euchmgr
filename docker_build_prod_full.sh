#!/usr/bin/env bash

set -x

docker build -t euchmgr:prod -f Dockerfile.prod --no-cache --progress plain .
