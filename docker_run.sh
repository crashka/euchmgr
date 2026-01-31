#!/usr/bin/env bash

set -e

if [[ "$#" -gt 1 ]] ; then
    echo "unexpected argument(s): ${@:2}"
    exit 1
fi

IMAGE=euchmgr
BASE_PORT=5050

if [[ "$#" -eq 1 ]] ; then
    if ! [[ "$1" =~ ^[0-9]+$ ]] ; then
        echo "only numeric instance names supported"
        exit 1
    fi

    INST="$1"
    SFX="-${INST}"
    PORT=$((${BASE_PORT} + ${INST}))
else
    INST=""
    SFX=""
    PORT="${BASE_PORT}"
fi

set -x

docker run --name "${IMAGE}${SFX}" -d -p ${PORT}:5050 \
       --hostname "${IMAGE}${SFX}" \
       --mount type=bind,src=/var/docker/app/config,dst=/app/config \
       --mount type=bind,src=/var/docker/app${INST}/data,dst=/app/data \
       --mount type=bind,src=/var/docker/app${INST}/log,dst=/app/log \
       "${IMAGE}"
