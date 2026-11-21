#!/bin/sh
set -eu
mkdir -p "${CLIPFORGE_DATA_DIR:-/app/data}"
chown clipforge:clipforge "${CLIPFORGE_DATA_DIR:-/app/data}"
exec gosu clipforge uvicorn app:app --host 0.0.0.0 --port "${PORT:-10000}" --workers 1
