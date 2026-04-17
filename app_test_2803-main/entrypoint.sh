#!/usr/bin/env bash
set -euo pipefail

if [[ "${RUN_MIGRATIONS:-true}" == "true" ]]; then
  echo "[entrypoint] running alembic upgrade head"
  alembic upgrade head
fi

exec "$@"
