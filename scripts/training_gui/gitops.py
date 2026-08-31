"""The fixed git sequences: save a run to a branch, and update from GitHub.

Two properties hold everything else up.

**The sequences are fixed.** No path, ref, branch name or flag in this module
comes from the browser. The page's two buttons carry no payload at all: the
branch name is derived from the run id, the base is the sha the manifest recorded
at run start, and the paths staged are the two literal prefixes ``reports`` and
``models``. There is deliberately no ``-A``, no merge, no rebase, no force and no
amend anywhere in this file (DD6/DD7).

**The base is the run's own commit, not ``origin/main`` (AD6).** A report is only
interpretable next to the code that produced it, and new experiments routinely
live on a branch before they are merged. When the machine is on an up-to-date
``main`` the two are the same commit; when it is not, the difference is between a
readable branch and one whose reports were produced by code it does not contain.
If that sha is not on the remote the push fails, and that failure is shown raw:
it is the correct answer, and it means "push your code branch first".

Both sequences are guarded before they mutate anything (AD7), because
``git checkout -b <new> <sha>`` aborts with "local changes would be overwritten"
whenever the current branch differs from the base in a file that is locally
modified -- which is the normal state after a run on a feature branch.

Every function returns a :class:`GitResult` carrying the ordered list of steps
attempted, each with its argv, exit code and captured output, so the page can
show exactly where a sequence stopped rather than a bare "it failed".
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .runner import DEFAULT_STATE_DIR, REPO_ROOT

#: A command runner: takes an argv list, returns its exit code and its combined
#: output. Injected so that the tests assert on assembled argv and sequencing
#: without a network or a real repository to mutate.
CommandRunner = Callable[[Sequence[str]], "tuple[int, str]"]

#: Where a saved run's log and manifest are committed (AD5). Deliberately outside
#: ``reports/encoder_training/``, whose README defines what is committed there;
#: console artefacts are metadata about an execution and do not belong in that
#: table.
RUN_ARTEFACT_DIR = "reports/training_runs"

#: The only two path prefixes ever staged.
COMMITTED_PREFIXES = ("reports", "models")

_SSH_REMOTE = re.compile(
    r"^(?:ssh://)?git@github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)
_HTTPS_REMOTE = re.compile(
    r"^https?://(?:[^@/]+@)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)


class GitOpsError(Exception):
    """The caller asked for something this module cannot assemble."""


@dataclass(frozen=True)
class GitStep:
    """One thing attempted, whether a git command or the artefact copy."""

    argv: tuple[str, ...]
    exit_code: int
    output: str
    kind: str = "git"

    def to_json(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "exit_code": self.exit_code,
            "output": self.output,
            "kind": self.kind,
        }


@dataclass
class GitResult:
    """The outcome of a sequence: what ran, how far it got, and what to show."""

    ok: bool
    message: str
    steps: list[GitStep] = field(default_factory=list)
    branch: str | None = None
    compare_url: str | None = None
    #: ``git commit`` found nothing staged. Not an error: the run wrote nothing.
    nothing_to_commit: bool = False
    #: Paths that blocked a guard, so the page can list them rather than quote a
    #: porcelain dump.
    blocking_paths: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "steps": [step.to_json() for step in self.steps],
            "branch": self.branch,
            "compare_url": self.compare_url,
            "nothing_to_commit": self.nothing_to_commit,
            "blocking_paths": list(self.blocking_paths),
        }


def default_runner(repo_root: Path | str = REPO_ROOT) -> CommandRunner:
    """A runner that shells out to ``git`` in ``repo_root``, stderr folded in."""
    root = Path(repo_root)

    def run(argv: Sequence[str]) -> tuple[int, str]:
        completed = subprocess.run(
            list(argv),
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode, (completed.stdout + completed.stderr).strip()

    return run


# ---------------------------------------------------------------------------
# porcelain
# ---------------------------------------------------------------------------


def _porcelain_paths(output: str) -> Iterator[str]:
    """Every path named by ``git status --porcelain``, renames counted twice.

    A rename is reported as ``old -> new``; both sides matter to the guard,
    because a rename out of ``reports/`` dirties something that is not ours.
    """
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else ""
        if not path:
            continue
        for part in path.split(" -> "):
            part = part.strip().strip('"')
            if part:
                yield part


def _outside_committed_prefixes(paths: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                path
                for path in paths
                if not any(
                    path == prefix or path.startswith(f"{prefix}/") for prefix in COMMITTED_PREFIXES
                )
            }
        )
    )


# ---------------------------------------------------------------------------
# save a run to a branch
# ---------------------------------------------------------------------------


def branch_name(manifest: Mapping[str, Any], today: date | None = None) -> str:
    """``training/<YYYY-MM-DD>-<run id>``.

    Unique by construction, because the run id carries a timestamp. The date is
    the run's own start date where the manifest records one, so a branch cut the
    morning after an overnight run is still filed under the night it ran.
    """
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise GitOpsError("manifest has no run_id")
    return f"training/{_run_date(manifest, today).isoformat()}-{run_id}"


def _run_date(manifest: Mapping[str, Any], today: date | None = None) -> date:
    started = manifest.get("started_at")
    if isinstance(started, str) and started:
        try:
            return datetime.fromisoformat(started).date()
        except ValueError:
            pass
    return today or date.today()


def commit_message(manifest: Mapping[str, Any], today: date | None = None) -> str:
    """Subject plus a body that makes the branch readable on its own (AD5).

    The body names the base sha, the resolved parameter values and every step's
    command line with its exit code, so a reviewer on a phone can see what was
    run and how it ended without opening the manifest.
    """
    run_date = _run_date(manifest, today).isoformat()
    name = manifest.get("entry_name") or manifest.get("entry_id") or "run"
    lines = [f"training run: {name} ({run_date})", ""]

    run_id = manifest.get("run_id")
    if run_id:
        lines.append(f"Run id: {run_id}")
    lines.append(f"Base commit: {manifest.get('commit') or 'unknown'}")
    lines.append(f"Status: {manifest.get('status') or 'unknown'}")

    parameters = manifest.get("parameters") or {}
    if isinstance(parameters, Mapping) and parameters:
        lines.append("")
        lines.append("Parameters:")
        lines.extend(f"  {key}={value}" for key, value in sorted(parameters.items()))

    steps = manifest.get("steps") or []
    if isinstance(steps, list) and steps:
        lines.append("")
        lines.append("Steps:")
        for step in steps:
            if not isinstance(step, Mapping):
                continue
            command = step.get("command") or " ".join(step.get("argv") or [])
            exit_code = step.get("exit_code")
            shown = "not run" if exit_code is None else f"exit {exit_code}"
            lines.append(f"  [{step.get('status', '?')}, {shown}] {command}")

    return "\n".join(lines) + "\n"


def save_run_to_branch(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path | str = REPO_ROOT,
    state_dir: Path | str | None = None,
    run_command: CommandRunner | None = None,
    today: date | None = None,
) -> GitResult:
    """Put this run's reports, models, log and manifest on a new branch.

    Guards first, then, stopping at the first non-zero exit: fetch, checkout -b
    from the manifest's sha, copy the artefacts in, add the two prefixes, commit,
    push.
    """
    root = Path(repo_root)
    state = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR
    run = run_command or default_runner(root)
    steps: list[GitStep] = []

    def issue(argv: Sequence[str]) -> tuple[int, str]:
        exit_code, output = run(list(argv))
        steps.append(GitStep(argv=tuple(argv), exit_code=exit_code, output=output))
        return exit_code, output

    branch = branch_name(manifest, today)
    base = manifest.get("commit")
    if not isinstance(base, str) or not base:
        return GitResult(
            ok=False,
            message=(
                "This run did not record the commit it was produced by, "
                "so there is no base to branch from."
            ),
            steps=steps,
        )

    # -- guard 1: nothing dirty outside reports/ and models/ (AD7) ------------
    exit_code, output = issue(["git", "status", "--porcelain"])
    if exit_code != 0:
        return GitResult(ok=False, message="git status failed.", steps=steps)
    blocking = _outside_committed_prefixes(_porcelain_paths(output))
    if blocking:
        return GitResult(
            ok=False,
            message=(
                "The working tree has changes outside reports/ and models/. "
                "Commit or stash them first: " + ", ".join(blocking)
            ),
            steps=steps,
            blocking_paths=blocking,
        )

    # -- guard 2: the repository has not moved since the run (AD7) -----------
    exit_code, output = issue(["git", "rev-parse", "HEAD"])
    if exit_code != 0:
        return GitResult(ok=False, message="git rev-parse HEAD failed.", steps=steps)
    head = output.strip()
    if head != base:
        return GitResult(
            ok=False,
            message=(
                f"The repository moved since this run: it was produced at {base}, "
                f"but HEAD is now {head}. Check out that commit before saving the run."
            ),
            steps=steps,
        )

    # -- the sequence proper -------------------------------------------------
    exit_code, _ = issue(["git", "fetch", "origin"])
    if exit_code != 0:
        return GitResult(ok=False, message="git fetch origin failed.", steps=steps)

    exit_code, _ = issue(["git", "checkout", "-b", branch, base])
    if exit_code != 0:
        return GitResult(ok=False, message=f"Could not create branch {branch}.", steps=steps)

    steps.append(_copy_artefacts(manifest, root, state))

    # The two literal prefixes, never -A, never a path from the browser.
    exit_code, _ = issue(["git", "add", "--", *COMMITTED_PREFIXES])
    if exit_code != 0:
        return GitResult(ok=False, message="git add failed.", steps=steps, branch=branch)

    exit_code, output = issue(["git", "commit", "-m", commit_message(manifest, today)])
    if exit_code != 0:
        if _is_nothing_to_commit(output):
            return GitResult(
                ok=False,
                message=(
                    "This run changed nothing under reports/ or models/, "
                    "so there is nothing to save."
                ),
                steps=steps,
                branch=branch,
                nothing_to_commit=True,
            )
        return GitResult(ok=False, message="git commit failed.", steps=steps, branch=branch)

    exit_code, _ = issue(["git", "push", "-u", "origin", branch])
    if exit_code != 0:
        return GitResult(
            ok=False,
            message=(
                f"git push failed. If the base commit {base} is not on GitHub yet, "
                "push the code branch it is on first."
            ),
            steps=steps,
            branch=branch,
        )

    return GitResult(
        ok=True,
        message=f"Saved to branch {branch}.",
        steps=steps,
        branch=branch,
        compare_url=_compare_url_for(branch, run),
    )


def _is_nothing_to_commit(output: str) -> bool:
    lowered = output.lower()
    return "nothing to commit" in lowered or "nothing added to commit" in lowered


def _copy_artefacts(manifest: Mapping[str, Any], root: Path, state_dir: Path) -> GitStep:
    """Copy the run's log and manifest into ``reports/training_runs/<run_id>/``.

    Not a git command, but part of the sequence, so it is recorded as a step too:
    a branch that holds the reports but not the commands that produced them is
    the thing AD5 exists to prevent.
    """
    run_id = str(manifest.get("run_id"))
    destination = root / RUN_ARTEFACT_DIR / run_id
    sources = [state_dir / f"{run_id}.log", state_dir / f"{run_id}.manifest.json"]
    copied: list[str] = []
    missing: list[str] = []
    try:
        destination.mkdir(parents=True, exist_ok=True)
        for source in sources:
            if source.exists():
                shutil.copy2(source, destination / source.name)
                copied.append(source.name)
            else:
                missing.append(source.name)
    except OSError as exc:
        return GitStep(
            argv=("copy", str(state_dir), str(destination)),
            exit_code=1,
            output=f"could not copy the run's artefacts: {exc}",
            kind="copy",
        )

    lines = [f"copied {', '.join(copied) or 'nothing'} to {RUN_ARTEFACT_DIR}/{run_id}/"]
    if missing:
        # Not fatal: the reports are still worth a branch. Said out loud so the
        # gap is visible on the page rather than only in the diff.
        lines.append(f"missing: {', '.join(missing)}")
    return GitStep(
        argv=("copy", str(state_dir), str(destination)),
        exit_code=0,
        output="\n".join(lines),
        kind="copy",
    )


def _compare_url_for(branch: str, run: CommandRunner) -> str | None:
    exit_code, output = run(["git", "remote", "get-url", "origin"])
    if exit_code != 0:
        return None
    return compare_url(output.strip(), branch)


def compare_url(remote_url: str, branch: str) -> str | None:
    """A GitHub compare link for ``branch``, or ``None`` for a remote we cannot read.

    Guessing a URL for an unrecognised remote would hand the user a 404 that
    looks like a broken run; the page shows the branch name alone instead.
    """
    remote_url = (remote_url or "").strip()
    match = _SSH_REMOTE.match(remote_url) or _HTTPS_REMOTE.match(remote_url)
    if not match:
        return None
    owner, repo = match.group("owner"), match.group("repo")
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}/compare/{branch}?expand=1"


# ---------------------------------------------------------------------------
# update from GitHub
# ---------------------------------------------------------------------------


def update_from_github(
    *,
    repo_root: Path | str = REPO_ROOT,
    run_command: CommandRunner | None = None,
) -> GitResult:
    """``git fetch origin`` then ``git pull --ff-only``, refused on any dirty tree.

    Any dirt at all, reports included: being clever about pulling around
    uncommitted reports is how a run gets lost. When the dirt is confined to
    ``reports/`` and ``models/`` the message says so, because the remedy is the
    other button on the page.
    """
    run = run_command or default_runner(Path(repo_root))
    steps: list[GitStep] = []

    def issue(argv: Sequence[str]) -> tuple[int, str]:
        exit_code, output = run(list(argv))
        steps.append(GitStep(argv=tuple(argv), exit_code=exit_code, output=output))
        return exit_code, output

    exit_code, output = issue(["git", "status", "--porcelain"])
    if exit_code != 0:
        return GitResult(ok=False, message="git status failed.", steps=steps)

    dirty = tuple(sorted(set(_porcelain_paths(output))))
    if dirty:
        outside = _outside_committed_prefixes(dirty)
        if outside:
            message = (
                "The working tree has uncommitted changes, so a pull could lose them. "
                "Commit or stash them first: " + ", ".join(dirty)
            )
        else:
            message = (
                "This run's output is not saved yet. Save this run to a branch first: "
                + ", ".join(dirty)
            )
        return GitResult(ok=False, message=message, steps=steps, blocking_paths=dirty)

    exit_code, _ = issue(["git", "fetch", "origin"])
    if exit_code != 0:
        return GitResult(ok=False, message="git fetch origin failed.", steps=steps)

    exit_code, output = issue(["git", "pull", "--ff-only"])
    if exit_code != 0:
        return GitResult(
            ok=False,
            message="git pull --ff-only failed. The local branch has diverged from the remote.",
            steps=steps,
        )
    return GitResult(ok=True, message=output.strip() or "Already up to date.", steps=steps)
