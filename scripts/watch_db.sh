#!/usr/bin/env bash
#
# Sample DB connection usage during a run — the "Watching during a run" check
# from RUNBOOK.md. Optional: not needed to load test, only to see how close
# you are to the connection-pool ceiling.
#
# Needs $DATABASE_URL (set it in config/<env>.env) and a local `psql`.
#
#     source config/local.env && scripts/watch_db.sh
#     WATCH_INTERVAL=5 scripts/watch_db.sh --env config/staging.env
#
set -euo pipefail

if [ "${1:-}" = "--env" ]; then
  [ -n "${2:-}" ] || { echo "--env needs a file path" >&2; exit 2; }
  # shellcheck disable=SC1090
  set -a; . "$2"; set +a; shift 2
fi

: "${DATABASE_URL:?set DATABASE_URL (e.g. in config/<env>.env) to monitor the DB}"
command -v psql >/dev/null 2>&1 || { echo "psql not found — install postgresql-client" >&2; exit 1; }

INTERVAL="${WATCH_INTERVAL:-15}"
maxc=$(psql "$DATABASE_URL" -tAc "show max_connections;" 2>/dev/null | tr -d '[:space:]' || echo '?')
echo "[watch-db] max_connections=$maxc — sampling every ${INTERVAL}s (Ctrl-C to stop)"

while true; do
  row=$(psql "$DATABASE_URL" -tAF',' -c \
    "select count(*) filter (where state='active'), count(*) from pg_stat_activity;" \
    2>/dev/null || echo "ERR,ERR")
  active="${row%%,*}"; total="${row##*,}"
  printf '%s  active=%s  total=%s / %s\n' "$(date +%H:%M:%S)" "$active" "$total" "$maxc"
  sleep "$INTERVAL"
done
