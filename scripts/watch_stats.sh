#!/usr/bin/env bash
#
# Sample per-container CPU/memory on the backend droplet during a run, so a
# category run (cat-light/medium/heavy/all) can be attributed to CPU vs memory
# and to Django vs Postgres. The CPU/memory companion to watch_db.sh.
#
# SSHes to $SSH_HOST and runs `docker stats --no-stream` with no container
# filter, so it auto-discovers every running container — no need to know the
# postgres/redis/celery container names. Appends a tidy CSV you can filter and
# plot afterward, and echoes each sample to stdout.
#
# Needs $SSH_HOST (set it in config/<env>.env) and SSH access to the droplet.
#
#     source config/staging.env && scripts/watch_stats.sh
#     WATCH_INTERVAL=5 scripts/watch_stats.sh --env config/staging.env
#     STATS_OUT=results/heavy_stats.csv scripts/watch_stats.sh --env config/staging.env
#
# CSV columns: time,container,cpu_perc,mem_usage,mem_perc,net_io,block_io
#   cpu_perc / mem_perc have the % stripped (numeric for plotting).
#   mem_usage / net_io / block_io are docker's raw "used / limit" strings.
#
set -euo pipefail

if [ "${1:-}" = "--env" ]; then
  [ -n "${2:-}" ] || { echo "--env needs a file path" >&2; exit 2; }
  # shellcheck disable=SC1090
  set -a; . "$2"; set +a; shift 2
fi

: "${SSH_HOST:?set SSH_HOST (e.g. in config/<env>.env) to sample the droplet}"
command -v ssh >/dev/null 2>&1 || { echo "ssh not found" >&2; exit 1; }

INTERVAL="${WATCH_INTERVAL:-5}"
OUT="${STATS_OUT:-results/watch_stats.csv}"
# shellcheck disable=SC2086  # SSH_OPTS is intentionally word-split
SSH=(ssh ${SSH_OPTS:-} "$SSH_HOST")

DOCKER_FMT='{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.MemPerc}}|{{.NetIO}}|{{.BlockIO}}'

mkdir -p "$(dirname "$OUT")"
if [ ! -s "$OUT" ]; then
  echo "time,container,cpu_perc,mem_usage,mem_perc,net_io,block_io" > "$OUT"
fi

echo "[watch-stats] $SSH_HOST — sampling every ${INTERVAL}s -> $OUT (Ctrl-C to stop)"
trap 'echo; echo "[watch-stats] stopped — wrote $OUT"; exit 0' INT TERM

while true; do
  ts="$(date +%Y-%m-%dT%H:%M:%S)"
  if ! raw="$("${SSH[@]}" "docker stats --no-stream --format '${DOCKER_FMT}'" 2>/dev/null)"; then
    printf '%s,SSH_ERROR,,,,,\n' "$ts" | tee -a "$OUT"
    sleep "$INTERVAL"
    continue
  fi
  # Prepend timestamp, strip % from cpu/mem so they plot as numbers.
  echo "$raw" | awk -F'|' -v ts="$ts" 'BEGIN{OFS=","}
      NF>=6 { gsub(/%/,"",$2); gsub(/%/,"",$4); print ts,$1,$2,$3,$4,$5,$6 }' \
    | tee -a "$OUT"
  sleep "$INTERVAL"
done
