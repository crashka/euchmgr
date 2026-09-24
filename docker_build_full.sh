#!/usr/bin/env bash

set -x

docker build -t euchmgr:admin-adj -f Dockerfile --no-cache --progress plain .
