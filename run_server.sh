#!/usr/bin/env bash

if [[ "${1,,}" == "proxied" ]] ; then
    SERVER="server:create_app(proxied=True)"
else
    SERVER="server:create_app()"
fi

set -x

gunicorn ${SERVER} --access-logfile=- --bind=0.0.0.0:5050 --threads=3
