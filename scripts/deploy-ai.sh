#!/bin/sh
# Opt-in only: temporary AWS credentials and all existing Free-plan guards apply.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$ROOT/infra/scripts/ai.py" deploy "$@"
