#!/usr/bin/env bash

set -x

flask --app server run --host=0.0.0.0 --port=5050 --debug
