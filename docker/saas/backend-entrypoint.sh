#!/bin/sh
# api: brings the database to the code's version (alembic), then serves the API behind the proxy.
# worker: the Celery worker sending the invoices to the AGT.
set -e
case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*" \
      --workers "${API_WORKERS:-2}"
    ;;
  worker)
    exec celery -A app.workers.celery_app worker --loglevel=info --concurrency "${WORKER_CONCURRENCY:-2}"
    ;;
  *)
    exec "$@"
    ;;
esac
