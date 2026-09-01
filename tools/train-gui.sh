#!/usr/bin/env bash
# Start the local training run console and open it in a browser.
#
# This script is the double-clickable front door (see tools/train-gui.bat, which
# calls it from Windows). It does four things and nothing else: put the shell in
# the repository root and the training environment, prove FastAPI is importable
# before uvicorn can fail obscurely, refuse to start a second console on a port
# that already has one, and open the page.
#
# It never touches training itself. Everything the console can run is declared in
# scripts/training_gui/runs.json.

set -euo pipefail

# The repository root is derived from this script's own path, never from the
# caller's working directory: double-clicking a shortcut starts you in
# C:\Windows\System32 or in $HOME, and `python -m scripts.training_gui...` only
# resolves from the root.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

HOST="${TRAIN_GUI_HOST:-127.0.0.1}"
PORT="${TRAIN_GUI_PORT:-8765}"
URL="http://${HOST}:${PORT}/"

# The environment that holds torch, and now fastapi and uvicorn as well (AD1).
# Override with TRAIN_GUI_CONDA_ENV if yours is named something else.
CONDA_ENV="${TRAIN_GUI_CONDA_ENV:-econsult-ml}"

activate_conda_env() {
  if [[ "${CONDA_DEFAULT_ENV:-}" == "${CONDA_ENV}" ]]; then
    return 0
  fi
  local conda_base
  if ! conda_base="$(conda info --base 2>/dev/null)"; then
    return 1
  fi
  # shellcheck disable=SC1091
  source "${conda_base}/etc/profile.d/conda.sh" 2>/dev/null || return 1
  conda activate "${CONDA_ENV}" 2>/dev/null || return 1
}

if ! activate_conda_env; then
  # Not fatal on its own: the console may be started from an already-correct
  # environment that conda does not know by that name. The preflight below is
  # the real gate, and it prints the remedy.
  echo "train-gui: could not activate the '${CONDA_ENV}' conda environment; using the current interpreter." >&2
fi

# Preflight (AD1). uvicorn's own failure for a missing FastAPI is a traceback in
# a window that closes; this is the pip line, and an exit code.
if ! python -c "import fastapi, uvicorn" >/dev/null 2>&1; then
  echo "train-gui: fastapi and uvicorn are not importable in this environment." >&2
  echo "train-gui: install the training dependencies with:" >&2
  echo >&2
  echo "    pip install -r requirements-ml.txt" >&2
  echo >&2
  exit 1
fi

# Refuse rather than let uvicorn die on "address already in use", which reads as
# a broken console rather than as a running one. Done in Python because ss, lsof
# and netstat are all optional on a minimal WSL image.
if ! python - "$HOST" "$PORT" <<'PY'
import socket
import sys

host, port = sys.argv[1], int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((host, port))
    except OSError:
        sys.exit(1)
sys.exit(0)
PY
then
  echo "train-gui: ${HOST}:${PORT} is already in use — the console is probably already running." >&2
  echo "train-gui: open ${URL}, or stop the other console first." >&2
  exit 1
fi

# Open the page. Under WSL2 the browser is the Windows one, so wslview and
# explorer.exe come first. None of these is worth failing the start over: if the
# page cannot be opened the URL is printed and the console still serves it.
open_browser() {
  if command -v wslview >/dev/null 2>&1; then
    wslview "${URL}" >/dev/null 2>&1 && return 0
  fi
  if command -v explorer.exe >/dev/null 2>&1; then
    # explorer.exe exits non-zero even when it succeeds; ignore its status.
    explorer.exe "${URL}" >/dev/null 2>&1 || true
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}" >/dev/null 2>&1 && return 0
  fi
  return 1
}

echo "train-gui: serving the training console at ${URL}"
echo "train-gui: closing this window stops the console, and stops any run it started."
(
  # Give uvicorn a moment to bind before the browser asks for the page.
  sleep 1
  if ! open_browser; then
    echo "train-gui: could not open a browser; go to ${URL}" >&2
  fi
) &

exec python -m uvicorn scripts.training_gui.server:app --host "${HOST}" --port "${PORT}"
