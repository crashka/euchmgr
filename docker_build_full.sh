#!/usr/bin/env bash

set -x

docker build -t euchmgr -f Dockerfile --no-cache --progress plain .
