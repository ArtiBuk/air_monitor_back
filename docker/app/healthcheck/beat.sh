#!/bin/sh
set -eu

pgrep -f "celery.*beat" >/dev/null
