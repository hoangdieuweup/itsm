#!/bin/sh
set -e

if [ -z "$WEB_CONCURRENCY" ]; then
    if [ "$ENV" = "prod" ]; then
        WEB_CONCURRENCY=4
    else
        WEB_CONCURRENCY=2
    fi
fi

exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "$WEB_CONCURRENCY" \
    --bind 0.0.0.0:8000 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
