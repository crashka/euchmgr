#!/usr/bin/env bash

set -x

docker build -t euchmgr -f Dockerfile --progress plain .
