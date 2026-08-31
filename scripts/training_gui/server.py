"""The HTTP layer: a catalogue id in, a run out, and a page to watch it on.

This module adds no knowledge of training and no new behaviour. It wires the
catalogue, the runner and the git sequences to nine endpoints and one page, and
it enforces DD4 at the boundary: **no endpoint accepts a command, an argument, a
path or a branch name from the browser.** A request carries a catalogue id and,
per declared parameter, one string that must be an exact match for a member of
that entry's committed ``choices``; the two git buttons carry no payload at all.
The id-rejection tests live at this layer as well as in ``catalogue.py`` on
purpose, because that guarantee is a property of the boundary rather than of the
loader.

``create_app`` takes its three collaborators as arguments so the tests can drive
fakes without a subprocess or a repository to mutate. The module-level ``app`` is
the same thing built from the real ones, for uvicorn.

The server binds ``127.0.0.1`` (the launcher passes the host; see
``tools/train-gui.sh``) and has no authentication: it is a local console for the
person sitting at the machine. If WSL2's localhost forwarding turns out not to
reach that bind from a Windows browser, binding the WSL interface instead is a
conscious follow-up decision, not a default to add pre-emptively.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from . import gitops as gitops_module
from .catalogue import CatalogueError, RunEntry, command_line, load_catalogue, resolve
from .runner import DEFAULT_STATE_DIR, REPO_ROOT, RUNNER, STATUS_RUNNING, RunnerBusy, RunnerError

#: The single page. One file, no build step.
STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"


class GitOps:
    """The two git sequences, bound to a repository, as an injectable object.

    ``gitops.py`` is a module of free functions taking ``repo_root`` and
    ``state_dir``; the endpoints want two no-argument-ish methods and the tests
    want something they can replace. This is that adapter and nothing else.
    """

    def __init__(
        self,
        repo_root: Path | str = REPO_ROOT,
        state_dir: Path | str | None = None,
    ):
        self.repo_root = Path(repo_root)
        self.state_dir = Path(state_dir) if state_dir is not None else DEFAULT_STATE_DIR

    def save_run_to_branch(self, manifest: Mapping[str, Any]) -> gitops_module.GitResult:
        return gitops_module.save_run_to_branch(
            manifest, repo_root=self.repo_root, state_dir=self.state_dir
        )

    def update_from_github(self) -> gitops_module.GitResult:
        return gitops_module.update_from_github(repo_root=self.repo_root)


# ---------------------------------------------------------------------------
# shaping
# ---------------------------------------------------------------------------


def _entry_json(entry: RunEntry) -> dict[str, Any]:
    """One catalogue entry, with its command lines rendered at current defaults.

    The page re-renders the lines itself as the dropdowns change, but it needs a
    starting point, and a page that shows the literal command before the click is
    the whole reason the catalogue is readable at all.
    """
    defaults = {parameter.name: parameter.default for parameter in entry.parameters}
    return {
        "id": entry.id,
        "name": entry.name,
        "description": entry.description,
        "parameters": [
            {
                "name": parameter.name,
                "label": parameter.label,
                "choices": list(parameter.choices),
                "default": parameter.default,
            }
            for parameter in entry.parameters
        ],
        # The raw steps travel too, so the page can substitute locally rather
        # than round-tripping to the server on every dropdown change.
        "steps": [list(step) for step in entry.steps],
        "commands": [command_line(argv) for argv in resolve(entry, defaults)],
    }


def _current_step(steps: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The step the page should be showing: the running one, else the last one
    that got as far as starting, else nothing."""
    for step in steps:
        if step.get("status") == STATUS_RUNNING:
            return step
    started = [step for step in steps if step.get("status") not in ("pending", "skipped")]
    return started[-1] if started else None


def _status_json(manifest: Mapping[str, Any]) -> dict[str, Any]:
    steps = manifest.get("steps") or []
    current = _current_step(steps) if isinstance(steps, list) else None
    return {
        **dict(manifest),
        "step_count": len(steps) if isinstance(steps, list) else 0,
        "step_index": current.get("index") if current else None,
        "command": current.get("command") if current else None,
    }


def _parameters_from(body: Mapping[str, Any]) -> dict[str, str]:
    """Reject a non-string value here rather than letting it reach ``resolve``.

    ``resolve`` would refuse it too -- nothing outside ``choices`` passes -- but a
    400 that names the offending key is a better answer than one that stringifies
    it first.
    """
    raw = body.get("parameters") or {}
    if not isinstance(raw, Mapping):
        raise HTTPException(status_code=400, detail="parameters must be an object")
    values: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"parameter {key!r} must be a string value")
        values[key] = value
    return values


# ---------------------------------------------------------------------------
# the app
# ---------------------------------------------------------------------------


def create_app(runner: Any, catalogue: Sequence[RunEntry], gitops: Any) -> FastAPI:
    """Build the console over the given collaborators."""
    app = FastAPI(title="Encoder training console", docs_url=None, redoc_url=None)
    entries = {entry.id: entry for entry in catalogue}

    def active_manifest() -> dict[str, Any]:
        return dict(runner.status() or {})

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(INDEX_PATH, media_type="text/html")

    @app.get("/api/catalogue")
    def get_catalogue() -> dict[str, Any]:
        return {"runs": [_entry_json(entry) for entry in catalogue]}

    @app.post("/api/run")
    def post_run(body: dict[str, Any] = Body(default={})) -> JSONResponse:
        entry_id = body.get("id")
        entry = entries.get(entry_id) if isinstance(entry_id, str) else None
        if entry is None:
            raise HTTPException(status_code=404, detail=f"no run named {entry_id!r}")

        values = _parameters_from(body)
        try:
            # Validation and display in one: whatever the page is told started is
            # exactly what the runner resolves for itself.
            commands = [command_line(argv) for argv in resolve(entry, values)]
        except CatalogueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        try:
            handle = runner.start(entry, values)
        except RunnerBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        return JSONResponse(
            status_code=202,
            content={
                "run_id": getattr(handle, "run_id", None),
                "entry_id": entry.id,
                "entry_name": entry.name,
                "commands": commands,
            },
        )

    @app.get("/api/status")
    def get_status() -> dict[str, Any]:
        return _status_json(active_manifest())

    @app.get("/api/log")
    def get_log(offset: int = Query(default=0, ge=0)) -> dict[str, Any]:
        run_id = active_manifest().get("run_id")
        if not run_id:
            return {"text": "", "next_offset": 0, "run_id": None}
        text, next_offset = runner.read_log(run_id, offset)
        return {"text": text, "next_offset": next_offset, "run_id": run_id}

    @app.post("/api/stop")
    def post_stop() -> dict[str, Any]:
        try:
            runner.stop()
        except RunnerError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"stopping": True}

    @app.get("/api/changes")
    def get_changes() -> dict[str, Any]:
        try:
            changed = runner.changed_paths()
        except RunnerError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {
            "changed": [
                {"path": item.path, "status": item.status, "untracked": item.untracked}
                for item in changed
            ]
        }

    @app.post("/api/save-branch")
    def post_save_branch() -> JSONResponse:
        manifest = active_manifest()
        if not manifest.get("run_id"):
            raise HTTPException(status_code=409, detail="there is no run to save")
        if manifest.get("status") == STATUS_RUNNING:
            raise HTTPException(status_code=409, detail="the run is still going")
        result = gitops.save_run_to_branch(manifest)
        # A failed sequence is a 200 carrying ok=false: the page's job is to show
        # the raw output of the step that stopped it, and an HTTP error code would
        # only encourage it to show a summary instead.
        return JSONResponse(status_code=200, content=result.to_json())

    @app.post("/api/update")
    def post_update() -> JSONResponse:
        return JSONResponse(status_code=200, content=gitops.update_from_github().to_json())

    return app


#: What uvicorn serves.
app = create_app(RUNNER, load_catalogue(), GitOps())
