#!/usr/bin/env bash

set -x

gunicorn server:"create_app()" --access-logfile=- --bind=0.0.0.0:5050 --threads=3
