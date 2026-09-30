#!/usr/bin/env bash

set -x

docker build -t euchmgr-dev -f Dockerfile.dev --no-cache --progress plain .
