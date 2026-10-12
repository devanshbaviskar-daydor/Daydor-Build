#!/usr/bin/env bash
# Re-syncs this repo with the backend sitting next to it, then runs every check.
#
#   common-folder/
#     daydor-backend/      <- the backend repo
#     daydor-frontend/     <- this repo
#
# Needs: Postgres 16 running, a superuser role daydor_owner (password "dev") or the URLs below set,
# Python 3.11+, Node 20+.
#
#   bash scripts/sync-from-backend.sh            # sync, then test everything
#   bash scripts/sync-from-backend.sh --no-test  # only sync
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="${DAYDOR_BACKEND_ROOT:-$HERE/../daydor-backend}"
[ -f "$BACKEND/model/daydor_model.json" ] || { echo "Cannot find the backend at $BACKEND (set DAYDOR_BACKEND_ROOT)"; exit 1; }
BACKEND="$(cd "$BACKEND" && pwd)"
export DAYDOR_BACKEND_ROOT="$BACKEND"
export DAYDOR_DATABASE_URL="${DAYDOR_DATABASE_URL:-postgresql+psycopg://daydor_owner:dev@localhost:5432/daydor_dev}"
export DAYDOR_API_TEST_DATABASE_URL="${DAYDOR_API_TEST_DATABASE_URL:-postgresql+psycopg://daydor_owner:dev@localhost:5432/daydor_api_test}"

# Use the active virtual environment, or create one next to this repo (system Python is often locked).
if [ -z "${VIRTUAL_ENV:-}" ]; then
  [ -d "$HERE/.venv" ] || python3 -m venv "$HERE/.venv"
  # shellcheck disable=SC1091
  source "$HERE/.venv/bin/activate"
fi
echo "== backend: $BACKEND"
echo "== python packages (in ${VIRTUAL_ENV})"
python3 -m pip install -q -e "$BACKEND" -e "$HERE/api[dev]"
echo "== enum values scanned from the backend"
(cd "$HERE/api" && python3 scripts/gen_enums.py "$BACKEND")
echo "== contract regenerated from the backend's model"
(cd "$HERE/frontend" && npm install --no-audit --no-fund --silent && npm run --silent contract:sync)

[ "${1:-}" = "--no-test" ] && exit 0
echo "== API tests (real Postgres, the backend's migrations)"
(cd "$HERE/api" && python3 -m pytest -q)
echo "== frontend typecheck, lint and tests"
(cd "$HERE/frontend" && npm run --silent typecheck && npm run --silent lint && npm test --silent)
echo "== done"
