#!/usr/bin/env bash
#
# Delete load-test users (loadtest+*@example.com) and their cascaded data from
# the target backend. Local docker or remote SSH, decided by $SSH_HOST — same
# config as seed.sh.
#
#     source config/staging.env && scripts/teardown.sh
#     scripts/teardown.sh --env config/staging.env
#     LOAD_TEST_DRY_RUN=1 scripts/teardown.sh        # preview only
#
set -euo pipefail

if [ "${1:-}" = "--env" ]; then
  [ -n "${2:-}" ] || { echo "--env needs a file path" >&2; exit 2; }
  # shellcheck disable=SC1090
  set -a; . "$2"; set +a; shift 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TD_SCRIPT="$ROOT/scripts/teardown_users.py"
CONTAINER="${DJANGO_CONTAINER:-easychef-dc01}"

ENVARGS=()
[ -n "${LOAD_TEST_DRY_RUN:-}" ] && ENVARGS=( -e "LOAD_TEST_DRY_RUN=$LOAD_TEST_DRY_RUN" )

if [ -n "${SSH_HOST:-}" ]; then
  echo "[teardown] remote=$SSH_HOST container=$CONTAINER dry_run=${LOAD_TEST_DRY_RUN:-0}"
  # shellcheck disable=SC2086  # SSH_OPTS is intentionally word-split
  ssh ${SSH_OPTS:-} "$SSH_HOST" "docker exec -i ${ENVARGS[*]:-} $CONTAINER python manage.py shell" < "$TD_SCRIPT"
else
  echo "[teardown] local container=$CONTAINER dry_run=${LOAD_TEST_DRY_RUN:-0}"
  docker exec -i ${ENVARGS[@]+"${ENVARGS[@]}"} "$CONTAINER" python manage.py shell < "$TD_SCRIPT"
fi
