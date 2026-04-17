#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  echo "[entrypoint] running alembic upgrade head"
  (cd /code/app && alembic upgrade head)
fi

exec "$@"
