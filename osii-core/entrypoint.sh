#!/usr/bin/env bash
set -e

# In production use gunicorn; fallback to flask run when gunicorn is missing
if command -v gunicorn > /dev/null; then
    exec gunicorn --workers 2 --bind 0.0.0.0:5000 "app:create_app()"
else
    exec flask run --host=0.0.0.0 --port=5000
fi