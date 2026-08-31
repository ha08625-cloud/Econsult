"""Execution: one run at a time, streamed to a log, recorded in a manifest.

A run is an ordered list of steps (AD4). A non-zero exit aborts the rest of them,
because continuing past a failed step produces a report tree that loads cleanly
and means nothing -- the exact failure ``generate-folds`` was scripted to avoid.
Every step's argv, exit code and timings go into the run manifest, which is
rewritten at every step boundary so that a crash leaves a truthful record rather
than a stale "running".

Three things here are load-bearing and easy to lose:

``-u``
    Without unbuffered output a twenty-minute step shows nothing in the log until
    it ends, which defeats the whole point of a live view.

``sys.executable``
    The interpreter the console itself is running under, which by AD1 is the
    training environment. Nothing else is ever executed as an interpreter.

``start_new_session=True``
    The child gets its own process group, so Stop can signal the whole tree
    (a training run spawns dataloader workers) and so killing the console kills
    the run. Closing the *browser* does not, which is the property that matters.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalogue import RunEntry, command_line, resolve

#: The repository root: scripts/training_gui/runner.py -> repo.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Logs, manifests and the state file. Git-ignored (``dev_output/``); the git
#: step copies the log and manifest into ``reports/training_runs/`` when a run is
#: saved to a branch (AD5).
DEFAULT_STATE_DIR = REPO_ROOT / "dev_output" / "training_gui"

#: Seconds between SIGTERM and SIGKILL when stopping a run.
STOP_GRACE_SECONDS = 10.0

#: How much of the child's output to move at a time. Small enough that the page
#: sees a line promptly, large enough not to syscall per byte.
_READ_CHUNK = 4096

STATUS_IDLE = "idle"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_STOPPED = "stopped"
STATUS_INTERRUPTED = "interrupted"

#: A run in one of these has finished, one way or another.
TERMINAL_STATUSES = frozenset(
    {
        STATUS_SUCCEEDED,
        STATUS_FAILED,
        STATUS_STOPPED,
        STATUS_INTERRUPTED,
    }
)


class RunnerBusy(Exception):
    """A run is already active."""


class RunnerError(Exception):
    """The runner cannot do what was asked."""


@dataclass(frozen=True)
class RunHandle:
    """What ``start`` hands back: enough to find the run's files."""

    run_id: str
    entry_id: str
    log_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class ChangedPath:
    """One line of ``git status --porcelain``, split."""

    path: str
    status: str

    @property
    def untracked(self) -> bool:
        return self.status == "??"


@dataclass
class _Step:
    index: int
    argv: list[str]
    command: str
    status: str = "pending"
    exit_code: int | None = None
    started_at: str | None = None
    ended_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "argv": list(self.argv),
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


@dataclass
class _Run:
    run_id: str
    entry_id: str
    entry_name: str
    parameters: dict[str, str]
    commit: str | None
    steps: list[_Step]
    status: str = STATUS_RUNNING
    started_at: str = ""
    ended_at: str | None = None
    error: str | None = None
    pid: int | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "entry_id": self.entry_id,
            "entry_name": self.entry_name,
            "parameters": dict(self.parameters),
            "commit": self.commit,
            "status": self.status,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "error": self.error,
            "steps": [step.to_json() for step in self.steps],
        }


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Someone else's process now holds the pid. Not ours either way, but it
        # is alive, so refusing to start on top of it is the safe reading.
        return True
    return True


class Runner:
    """Runs one catalogue entry at a time in ``repo_root``.

    A single instance is shared by the server (see :data:`RUNNER`). Tests build
    their own against a ``tmp_path`` so that no test ever touches the real
    ``dev_output/``.
    """

    def __init__(self, repo_root: Path | str = REPO_ROOT, state_dir: Path | str | None = None):
        self.repo_root = Path(repo_root)
        self.state_dir = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._stop_requested = False
        self._run: _Run | None = None

    # -- paths ---------------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.state_dir / "state.json"

    def log_path(self, run_id: str) -> Path:
        return self.state_dir / f"{run_id}.log"

    def manifest_path(self, run_id: str) -> Path:
        return self.state_dir / f"{run_id}.manifest.json"

    # -- starting ------------------------------------------------------------

    def start(self, entry: RunEntry, values: Mapping[str, str] | None = None) -> RunHandle:
        """Begin ``entry``. Raises :class:`RunnerBusy` if a run is already active.

        The liveness reconciliation runs first, so a state file left behind by a
        killed console does not wedge the machine into refusing every run.
        """
        with self._lock:
            active = self._reconcile_locked()
            if active is not None and active.get("status") == STATUS_RUNNING:
                raise RunnerBusy(f"run {active.get('run_id')} is already running")

            resolved_values = self._resolved_values(entry, values or {})
            argvs = resolve(entry, values or {})

            self.state_dir.mkdir(parents=True, exist_ok=True)
            run_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{entry.id}"
            run = _Run(
                run_id=run_id,
                entry_id=entry.id,
                entry_name=entry.name,
                parameters=resolved_values,
                commit=self._head_commit(),
                steps=[
                    _Step(index=position + 1, argv=list(argv), command=command_line(argv))
                    for position, argv in enumerate(argvs)
                ],
                started_at=_now(),
            )
            self._run = run
            self._stop_requested = False
            self._process = None

            self.log_path(run_id).write_bytes(b"")
            self._write_manifest_locked(run)
            self._write_state_locked(run)

            thread = threading.Thread(target=self._execute, args=(run,), daemon=True)
            self._thread = thread
            thread.start()

            return RunHandle(
                run_id=run_id,
                entry_id=entry.id,
                log_path=self.log_path(run_id),
                manifest_path=self.manifest_path(run_id),
            )

    @staticmethod
    def _resolved_values(entry: RunEntry, values: Mapping[str, str]) -> dict[str, str]:
        return {
            parameter.name: values.get(parameter.name, parameter.default)
            for parameter in entry.parameters
        }

    def _head_commit(self) -> str | None:
        """The sha the run was produced by, captured before the first step (AD6)."""
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip() or None

    # -- execution -----------------------------------------------------------

    def _execute(self, run: _Run) -> None:
        log = self.log_path(run.run_id)
        final_status = STATUS_SUCCEEDED
        try:
            with log.open("ab", buffering=0) as sink:
                for step in run.steps:
                    if self._stop_requested:
                        step.status = "skipped"
                        final_status = STATUS_STOPPED
                        break
                    outcome = self._run_step(run, step, sink)
                    if outcome != STATUS_SUCCEEDED:
                        final_status = outcome
                        break
                else:
                    final_status = STATUS_SUCCEEDED
                # Anything after an abort is recorded as unrun, not left pending.
                for step in run.steps:
                    if step.status == "pending":
                        step.status = "skipped"
                self._write_banner(sink, f"run {final_status}")
        except Exception as exc:  # pragma: no cover - defensive
            run.error = f"{type(exc).__name__}: {exc}"
            final_status = STATUS_FAILED

        with self._lock:
            run.status = final_status
            run.ended_at = _now()
            run.pid = None
            self._process = None
            self._write_manifest_locked(run)
            self._write_state_locked(run)

    def _run_step(self, run: _Run, step: _Step, sink: Any) -> str:
        step.status = STATUS_RUNNING
        step.started_at = _now()
        with self._lock:
            self._write_manifest_locked(run)
        self._write_banner(sink, f"step {step.index}/{len(run.steps)}: {step.command}")

        try:
            process = subprocess.Popen(
                [sys.executable, "-u", *step.argv],
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as exc:
            step.status = STATUS_FAILED
            step.exit_code = None
            step.ended_at = _now()
            run.error = f"could not start step {step.index}: {exc}"
            self._write_banner(sink, run.error)
            with self._lock:
                self._write_manifest_locked(run)
            return STATUS_FAILED

        with self._lock:
            self._process = process
            run.pid = process.pid
            self._write_state_locked(run)
            # Stop can arrive in the window between the flag being read at the
            # top of this method and the child existing. Without this the signal
            # lands on nothing and the step runs to completion regardless.
            stop_now = self._stop_requested
        if stop_now:
            self._signal_group(process, signal.SIGTERM)

        assert process.stdout is not None
        while True:
            chunk = process.stdout.read1(_READ_CHUNK)
            if not chunk:
                break
            sink.write(chunk)
        process.stdout.close()
        exit_code = process.wait()

        step.exit_code = exit_code
        step.ended_at = _now()
        if self._stop_requested:
            step.status = STATUS_STOPPED
            outcome = STATUS_STOPPED
        elif exit_code == 0:
            step.status = STATUS_SUCCEEDED
            outcome = STATUS_SUCCEEDED
        else:
            step.status = STATUS_FAILED
            outcome = STATUS_FAILED

        with self._lock:
            run.pid = None
            self._process = None
            self._write_manifest_locked(run)
        return outcome

    @staticmethod
    def _write_banner(sink: Any, text: str) -> None:
        sink.write(f"\n=== {text} ===\n".encode())

    # -- stopping ------------------------------------------------------------

    def stop(self) -> None:
        """Stop the active run: SIGTERM the process group, SIGKILL after a grace."""
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                raise RunnerError("no run is active")
            self._stop_requested = True
            process = self._process

        if process is None or process.poll() is not None:
            return
        self._signal_group(process, signal.SIGTERM)

        deadline = time.monotonic() + STOP_GRACE_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.1)
        self._signal_group(process, signal.SIGKILL)

    @staticmethod
    def _signal_group(process: subprocess.Popen[bytes], sig: int) -> None:
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            with contextlib.suppress(ProcessLookupError, OSError):
                process.send_signal(sig)

    def wait(self, timeout: float | None = None) -> None:
        """Block until the active run finishes. For tests and for shutdown."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    # -- reading -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """The current run's manifest, reconciled against process liveness."""
        with self._lock:
            active = self._reconcile_locked()
        if active is None:
            return {"status": STATUS_IDLE, "run_id": None}
        return active

    def read_log(self, run_id: str, offset: int = 0) -> tuple[str, int]:
        """Bytes from ``offset`` on. Returns the text and the next offset.

        Byte offsets rather than line counts because the page polls this while a
        step is mid-line, and the file must not be held open between polls.
        """
        path = self.log_path(run_id)
        if not path.exists():
            return "", 0
        size = path.stat().st_size
        if offset < 0 or offset > size:
            # The log was truncated or replaced under us; start again rather than
            # showing a slice from the wrong place.
            offset = 0
        with path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
        return data.decode("utf-8", errors="replace"), offset + len(data)

    def changed_paths(self) -> tuple[ChangedPath, ...]:
        """What the run wrote under ``reports/`` and ``models/``, untracked included."""
        completed = subprocess.run(
            ["git", "status", "--porcelain", "--", "reports", "models"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RunnerError(f"git status failed: {completed.stderr.strip()}")

        changed: list[ChangedPath] = []
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            status, _, path = line[:2], line[2:3], line[3:]
            if not path:
                continue
            # A rename is reported as "old -> new"; the new path is the one the
            # page is about to show and commit.
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            changed.append(ChangedPath(path=path.strip('"'), status=status.strip() or status))
        return tuple(changed)

    # -- state ---------------------------------------------------------------

    def _write_manifest_locked(self, run: _Run) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path(run.run_id).write_text(
            json.dumps(run.to_json(), indent=2) + "\n", encoding="utf-8"
        )

    def _write_state_locked(self, run: _Run) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps({"run_id": run.run_id, "pid": run.pid, "status": run.status}, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def _reconcile_locked(self) -> dict[str, Any] | None:
        """Return the active run's manifest, correcting a stale ``running`` (AD8).

        A console that was killed leaves ``state.json`` claiming a run that no
        longer exists. Since the child shares the console's process group death,
        a dead pid means the run died with it: that is ``interrupted``, which the
        page shows distinctly from ``failed`` because nothing about the training
        itself went wrong.
        """
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        run_id = state.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return None

        try:
            manifest = json.loads(self.manifest_path(run_id).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

        if manifest.get("status") != STATUS_RUNNING:
            return manifest

        ours = self._thread is not None and self._thread.is_alive()
        if ours or _pid_alive(state.get("pid")):
            return manifest

        manifest["status"] = STATUS_INTERRUPTED
        manifest["ended_at"] = manifest.get("ended_at") or _now()
        for step in manifest.get("steps", []):
            if step.get("status") == STATUS_RUNNING:
                step["status"] = STATUS_INTERRUPTED
            elif step.get("status") == "pending":
                step["status"] = "skipped"
        self.manifest_path(run_id).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        self.state_path.write_text(
            json.dumps({"run_id": run_id, "pid": None, "status": STATUS_INTERRUPTED}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return manifest


#: The instance the server uses. Tests build their own against ``tmp_path``.
RUNNER = Runner()
