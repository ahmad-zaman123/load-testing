#!/usr/bin/env bash
#
# Seed load-test users into the target backend, then pull the resulting
# tokens.json into ./fixtures/. Works against a LOCAL docker backend or a
# REMOTE one over SSH — decided entirely by $SSH_HOST.
#
# Config comes from the environment. Either source a config file first:
#     source config/staging.env && scripts/seed.sh
# or pass one explicitly:
#     scripts/seed.sh --env config/staging.env
# See config/*.env.example for every variable.
#
# NOTE: seeding runs scripts/seed_users.py *inside* the backend's Django shell
# because it uses the ORM and model signals. It never connects to the DB
# directly — so there's no DB credential involved here.
#
set -euo pipefail

if [ "${1:-}" = "--env" ]; then
  [ -n "${2:-}" ] || { echo "--env needs a file path" >&2; exit 2; }
  # shellcheck disable=SC1090
  set -a; . "$2"; set +a; shift 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SEED_SCRIPT="$ROOT/scripts/seed_users.py"

CONTAINER="${DJANGO_CONTAINER:-easychef-dc01}"
LOCAL_FIXTURE="${LOAD_TEST_TOKEN_FIXTURE:-fixtures/tokens.json}"
REMOTE_FIXTURE="${REMOTE_FIXTURE_PATH:-/tmp/load_test_tokens.json}"
COUNT="${LOAD_TEST_COUNT:-100}"
PANTRY="${LOAD_TEST_PANTRY_ITEMS:-110}"

# env injected into the container's Django process
ENVARGS=( -e "LOAD_TEST_COUNT=$COUNT" -e "LOAD_TEST_PANTRY_ITEMS=$PANTRY" -e "LOAD_TEST_OUTPUT=$REMOTE_FIXTURE" )

mkdir -p "$(dirname "$LOCAL_FIXTURE")"

if [ -n "${SSH_HOST:-}" ]; then
  echo "[seed] remote=$SSH_HOST container=$CONTAINER count=$COUNT pantry=$PANTRY"
  # shellcheck disable=SC2086  # SSH_OPTS is intentionally word-split
  ssh ${SSH_OPTS:-} "$SSH_HOST" "docker exec -i ${ENVARGS[*]} $CONTAINER python manage.py shell" < "$SEED_SCRIPT"
  ssh ${SSH_OPTS:-} "$SSH_HOST" "docker cp $CONTAINER:$REMOTE_FIXTURE /tmp/lt_tokens.json"
  scp ${SSH_OPTS:-} "$SSH_HOST:/tmp/lt_tokens.json" "$LOCAL_FIXTURE"
else
  echo "[seed] local container=$CONTAINER count=$COUNT pantry=$PANTRY"
  docker exec -i "${ENVARGS[@]}" "$CONTAINER" python manage.py shell < "$SEED_SCRIPT"
  docker cp "$CONTAINER:$REMOTE_FIXTURE" "$LOCAL_FIXTURE"
fi

n=$(python3 -c "import json;print(len(json.load(open('$LOCAL_FIXTURE'))['tokens']))" 2>/dev/null || echo '?')
echo "[seed] wrote $LOCAL_FIXTURE ($n tokens)"
