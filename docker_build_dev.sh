#!/usr/bin/env bash

set -x

docker build -t euchmgr-dev:admin-adj -f Dockerfile.dev --progress plain .
