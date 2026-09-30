#!/usr/bin/env bash

if [[ "${1,,}" == "proxied" ]] ; then
    SERVER="server:create_app(proxied=True)"
else
    SERVER="server"
fi

set -x

flask --app ${SERVER} run --port=5050 --debug
