#!/usr/bin/env bash
#
# A one-at-a-time job runner for overnight GPU work. See README.md.
#
# Jobs are executable shell scripts in gpu_queue/jobs/, run in filename order.
# A job that fails does not stop the queue: the tickets are independent, and
# losing three runs to the first one's typo is the failure mode this exists to
# prevent.

set -uo pipefail   # deliberately NOT -e: a failing job must not kill the runner

cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1
ROOT="$PWD"
Q="$ROOT/gpu_queue"

WATCH=0
MIN_FREE_GB=${MIN_FREE_GB:-20}
POLL=${POLL:-60}

for arg in "$@"; do
  case "$arg" in
    --watch) WATCH=1 ;;
    --help|-h)
      sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
      echo
      echo "usage: gpu_queue/run.sh [--watch]"
      echo "  --watch   keep waiting for new jobs instead of exiting when the queue drains"
      echo "env: MIN_FREE_GB (default 20), POLL (default 60 seconds)"
      exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

next_job() {
  find "$Q/jobs" -maxdepth 1 -name '*.sh' -type f 2>/dev/null | sort | head -1
}

free_gb() {
  df -BG --output=avail "$ROOT" 2>/dev/null | tail -1 | tr -dc '0-9'
}

run_one() {
  local job="$1" name stamp log started finished status avail
  name="$(basename "$job" .sh)"
  stamp="$(date +%Y%m%d-%H%M%S)"
  log="$Q/logs/${stamp}-${name}.log"

  avail="$(free_gb)"
  if [ -n "$avail" ] && [ "$avail" -lt "$MIN_FREE_GB" ]; then
    echo "[$(date +%H:%M:%S)] SKIP $name -- only ${avail}GB free, need ${MIN_FREE_GB}GB" | tee -a "$log"
    mv "$job" "$Q/failed/"
    return
  fi

  mv "$job" "$Q/running/" || return
  job="$Q/running/$(basename "$job")"

  {
    echo "=== job:        $name"
    echo "=== started:    $(date -Is)"
    echo "=== git:        $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null) on $(git -C "$ROOT" branch --show-current 2>/dev/null)"
    echo "=== git status: $(git -C "$ROOT" status --porcelain 2>/dev/null | wc -l) uncommitted file(s)"
    echo "=== free disk:  ${avail}GB"
    echo "=== gpu:        $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo 'nvidia-smi unavailable')"
    echo "=== key libs:   $(python -c 'import torch,transformers;print("torch",torch.__version__,"transformers",transformers.__version__)' 2>/dev/null || echo unknown)"
    echo "=== ---------- job output below ----------"
  } >> "$log"

  echo "[$(date +%H:%M:%S)] START $name  (log: ${log#"$ROOT"/})"
  started=$(date +%s)
  bash "$job" >> "$log" 2>&1
  status=$?
  finished=$(date +%s)

  {
    echo "=== ---------- job output above ----------"
    echo "=== exit status: $status"
    echo "=== finished:    $(date -Is)"
    echo "=== elapsed:     $(( (finished - started) / 60 )) min"
  } >> "$log"

  if [ "$status" -eq 0 ]; then
    mv "$job" "$Q/done/"
    echo "[$(date +%H:%M:%S)] DONE  $name  ($(( (finished - started) / 60 )) min)"
  else
    mv "$job" "$Q/failed/"
    echo "[$(date +%H:%M:%S)] FAIL  $name  (exit $status, $(( (finished - started) / 60 )) min) -- see ${log#"$ROOT"/}"
  fi
}

echo "queue runner started $(date -Is); jobs dir: gpu_queue/jobs/"
[ "$WATCH" -eq 1 ] && echo "watching -- add jobs any time; ctrl-c to stop"

while true; do
  job="$(next_job)"
  if [ -n "$job" ]; then
    run_one "$job"
    continue
  fi
  if [ "$WATCH" -eq 1 ]; then
    sleep "$POLL"
  else
    echo "queue empty; runner finished $(date -Is)"
    break
  fi
done
