#!/bin/sh
# Secrets arrive as swarm secrets at /run/secrets/trains_rail_key and
# /run/secrets/trains_tfl_key; export them as the env vars the app reads.
set -eu
if [ -f /run/secrets/trains_rail_key ]; then
    RAIL_API_KEY="$(cat /run/secrets/trains_rail_key)"
    export RAIL_API_KEY
fi
if [ -f /run/secrets/trains_tfl_key ]; then
    TFL_APP_KEY="$(cat /run/secrets/trains_tfl_key)"
    export TFL_APP_KEY
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
