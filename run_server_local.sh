#!/usr/bin/env bash

set -x

flask --app server run --port=5050 --debug
