#!/bin/sh
# Deletes only AI stack and AI ECR/images; explicit confirmation is mandatory.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec python3 "$ROOT/infra/scripts/ai.py" destroy "$@"
