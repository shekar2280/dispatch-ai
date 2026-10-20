#!/bin/bash
set -e

if [ "$#" -eq 0 ]; then
    set -- uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws wsproto --log-level info
fi
if [ "${ENVIRONMENT:-development}" = "development" ] && [ "${RELOAD:-false}" = "true" ]; then
    set -- "$@" --reload
fi
exec "$@"
