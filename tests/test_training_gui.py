"""Unit tests for the local run console's catalogue and runner.

Pure unit tests: no database, no torch, no GPU, no marker. The subprocesses the
runner tests start are stdlib module invocations (``-m json.tool``,
``-m timeit``) that finish instantly on any runner, so the execution path -- the
part that decides whether a failed step silently poisons a report tree -- is
covered by CI's ordinary unit job rather than only on the training machine.

Every runner test builds its own :class:`Runner` against ``tmp_path``. Nothing
here touches the real ``dev_output/training_gui/``.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.training_gui.catalogue import (
    DEFAULT_CATALOGUE_PATH,
    CatalogueError,
    Parameter,
    RunEntry,
    command_line,
    load_catalogue,
    resolve,
)
from scripts.training_gui.gitops import (
    GitOpsError,
    branch_name,
    commit_message,
    compare_url,
    save_run_to_branch,
    update_from_github,
)
from scripts.training_gui.runner import (
    STATUS_FAILED,
    STATUS_IDLE,
    STATUS_INTERRUPTED,
    STATUS_RUNNING,
    STATUS_STOPPED,
    STATUS_SUCCEEDED,
    Runner,
    RunnerBusy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def write_catalogue(path: Path, *runs: dict) -> Path:
    path.write_text(json.dumps({"runs": list(runs)}), encoding="utf-8")
    return path


def minimal_run(**overrides) -> dict:
    run = {
        "id": "example",
        "name": "Example",
        "description": "An example run.",
        "steps": [["-m", "scripts.encoder_training", "smoke-cuda"]],
    }
    run.update(overrides)
    return run


def sleeping_entry(seconds: float = 30.0) -> RunEntry:
    """A step that blocks until signalled. ``timeit`` is stdlib and portable."""
    return RunEntry(
        id="sleep",
        name="Sleep",
        description="blocks",
        steps=(("-m", "timeit", "-n", "1", "-r", "1", f"import time; time.sleep({seconds})"),),
    )


def wait_for(predicate, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


# ---------------------------------------------------------------------------
# the committed catalogue
# ---------------------------------------------------------------------------


def test_the_committed_catalogue_loads():
    entries = load_catalogue(DEFAULT_CATALOGUE_PATH)
    assert [entry.id for entry in entries] == [
        "smoke-cuda",
        "score-companions",
        "generate-folds",
        "merge-folds",
        "finetune",
    ]


def test_the_committed_catalogue_names_the_base_model_explicitly():
    """``DEFAULT_BASE_MODEL`` is Bio_ClinicalBERT, so omitting ``--base-model``
    produces a run that succeeds and yields numbers that cannot be read beside a
    committed report. Baking the flag in is one of the clearer things the console
    buys, and it is worth a test rather than a comment."""
    finetune = next(e for e in load_catalogue(DEFAULT_CATALOGUE_PATH) if e.id == "finetune")
    assert "--base-model" in finetune.steps[0]
    base_model = finetune.parameter("base_model")
    assert base_model is not None
    assert base_model.default == "roberta-base"


def test_every_committed_step_is_a_module_invocation():
    for entry in load_catalogue(DEFAULT_CATALOGUE_PATH):
        for step in entry.steps:
            assert step[0] == "-m", entry.id


# ---------------------------------------------------------------------------
# catalogue rejections
# ---------------------------------------------------------------------------


def test_missing_catalogue_is_named(tmp_path):
    with pytest.raises(CatalogueError, match="not found"):
        load_catalogue(tmp_path / "absent.json")


def test_invalid_json_is_reported_as_such(tmp_path):
    path = tmp_path / "runs.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CatalogueError, match="not valid JSON"):
        load_catalogue(path)


def test_catalogue_without_a_runs_list_is_rejected(tmp_path):
    path = tmp_path / "runs.json"
    path.write_text(json.dumps({"entries": []}), encoding="utf-8")
    with pytest.raises(CatalogueError, match="'runs' list"):
        load_catalogue(path)


def test_empty_catalogue_is_rejected(tmp_path):
    with pytest.raises(CatalogueError, match="declares no runs"):
        load_catalogue(write_catalogue(tmp_path / "runs.json"))


def test_duplicate_ids_are_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(), minimal_run())
    with pytest.raises(CatalogueError, match="duplicate run id 'example'"):
        load_catalogue(path)


def test_an_id_outside_the_allowed_alphabet_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(id="Smoke CUDA"))
    with pytest.raises(CatalogueError, match=r"must match \[a-z0-9-\]\+"):
        load_catalogue(path)


def test_an_empty_name_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(name="  "))
    with pytest.raises(CatalogueError, match="empty name"):
        load_catalogue(path)


def test_an_empty_description_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(description=""))
    with pytest.raises(CatalogueError, match="empty description"):
        load_catalogue(path)


def test_an_entry_with_no_steps_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(steps=[]))
    with pytest.raises(CatalogueError, match="steps must be a non-empty list"):
        load_catalogue(path)


def test_an_empty_step_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(steps=[[]]))
    with pytest.raises(CatalogueError, match="step 1 must be a non-empty list"):
        load_catalogue(path)


def test_a_non_string_step_element_is_rejected(tmp_path):
    path = write_catalogue(
        tmp_path / "runs.json", minimal_run(steps=[["-m", "scripts.encoder_training", 5]])
    )
    with pytest.raises(CatalogueError, match="non-string or empty element"):
        load_catalogue(path)


def test_a_step_naming_an_interpreter_is_rejected(tmp_path):
    """AD2. ``python`` is whatever the launcher's PATH holds, and on this project
    the wrong one fails as a SyntaxError inside recombine.py rather than as a
    configuration error."""
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(steps=[["python", "-m", "scripts.encoder_training", "smoke-cuda"]]),
    )
    with pytest.raises(CatalogueError, match="must begin with '-m'"):
        load_catalogue(path)


def test_a_step_naming_git_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(steps=[["git", "push"]]))
    with pytest.raises(CatalogueError, match="must begin with '-m'"):
        load_catalogue(path)


def test_a_step_with_no_module_after_dash_m_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(steps=[["-m"]]))
    with pytest.raises(CatalogueError, match="names no module"):
        load_catalogue(path)


def test_a_parameter_without_choices_is_rejected(tmp_path):
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(
            parameters=[{"name": "signal", "label": "Signal", "choices": [], "default": "x"}],
            steps=[["-m", "scripts.encoder_training", "--signal", "{signal}"]],
        ),
    )
    with pytest.raises(CatalogueError, match="has no choices"):
        load_catalogue(path)


def test_a_parameter_with_duplicate_choices_is_rejected(tmp_path):
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(
            parameters=[
                {"name": "signal", "label": "Signal", "choices": ["a", "a"], "default": "a"}
            ],
            steps=[["-m", "scripts.encoder_training", "--signal", "{signal}"]],
        ),
    )
    with pytest.raises(CatalogueError, match="duplicate choices"):
        load_catalogue(path)


def test_a_default_outside_the_choices_is_rejected(tmp_path):
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(
            parameters=[
                {"name": "signal", "label": "Signal", "choices": ["a", "b"], "default": "c"}
            ],
            steps=[["-m", "scripts.encoder_training", "--signal", "{signal}"]],
        ),
    )
    with pytest.raises(CatalogueError, match="is not one of its choices"):
        load_catalogue(path)


def test_a_parameter_name_that_is_not_identifier_ish_is_rejected(tmp_path):
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(
            parameters=[{"name": "Signal!", "label": "S", "choices": ["a"], "default": "a"}],
            steps=[["-m", "scripts.encoder_training"]],
        ),
    )
    with pytest.raises(CatalogueError, match="must match"):
        load_catalogue(path)


def test_an_undeclared_placeholder_is_rejected(tmp_path):
    """A crash at run time otherwise, hours after the button was pressed."""
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(steps=[["-m", "scripts.encoder_training", "--signal", "{signal}"]]),
    )
    with pytest.raises(CatalogueError, match="undeclared parameters: signal"):
        load_catalogue(path)


def test_a_parameter_no_step_uses_is_rejected(tmp_path):
    """The other direction: a dropdown that does nothing."""
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(
            parameters=[{"name": "signal", "label": "S", "choices": ["a"], "default": "a"}],
            steps=[["-m", "scripts.encoder_training", "smoke-cuda"]],
        ),
    )
    with pytest.raises(CatalogueError, match="appear in no step: signal"):
        load_catalogue(path)


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


@pytest.fixture
def parametrised_entry() -> RunEntry:
    return RunEntry(
        id="finetune",
        name="Fine-tune",
        description="one signal",
        steps=(
            ("-m", "scripts.encoder_training", "finetune", "--signal", "{signal}"),
            ("-m", "scripts.encoder_training", "--data-dir", "data/synthetic/generated/{tree}"),
        ),
        parameters=(
            Parameter("signal", "Signal", ("fever_present", "nocturia_present"), "fever_present"),
            Parameter("tree", "Tree", ("folds", "folds-volume"), "folds"),
        ),
    )


def test_resolve_substitutes_every_occurrence(parametrised_entry):
    steps = resolve(parametrised_entry, {"signal": "nocturia_present", "tree": "folds-volume"})
    assert steps[0][-1] == "nocturia_present"
    assert steps[1][-1] == "data/synthetic/generated/folds-volume"


def test_resolve_applies_defaults(parametrised_entry):
    steps = resolve(parametrised_entry, {})
    assert steps[0][-1] == "fever_present"
    assert steps[1][-1] == "data/synthetic/generated/folds"


def test_resolve_rejects_a_value_outside_the_choices(parametrised_entry):
    with pytest.raises(CatalogueError, match="is not an allowed value for 'signal'"):
        resolve(parametrised_entry, {"signal": "fever_present; rm -rf /"})


def test_resolve_rejects_an_unknown_key(parametrised_entry):
    """Ignoring it would let a stale page run something other than it displayed."""
    with pytest.raises(CatalogueError, match="unknown parameters: epochs"):
        resolve(parametrised_entry, {"epochs": "3"})


def test_command_line_is_the_line_a_human_would_type(parametrised_entry):
    line = command_line(resolve(parametrised_entry, {})[0])
    assert line == ("python -u -m scripts.encoder_training finetune --signal fever_present")


# ---------------------------------------------------------------------------
# the runner
# ---------------------------------------------------------------------------


@pytest.fixture
def runner(tmp_path) -> Runner:
    return Runner(repo_root=REPO_ROOT, state_dir=tmp_path / "training_gui")


def test_a_two_step_run_reaches_succeeded(runner):
    entry = RunEntry(
        id="two-step",
        name="Two steps",
        description="stdlib only",
        steps=(
            ("-m", "json.tool", "--help"),
            ("-m", "timeit", "-n", "1", "-r", "1", "pass"),
        ),
    )
    handle = runner.start(entry)
    runner.wait(timeout=60)

    status = runner.status()
    assert status["status"] == STATUS_SUCCEEDED
    assert [step["status"] for step in status["steps"]] == [STATUS_SUCCEEDED, STATUS_SUCCEEDED]
    assert [step["exit_code"] for step in status["steps"]] == [0, 0]
    assert status["run_id"] == handle.run_id
    assert status["started_at"] and status["ended_at"]

    manifest = json.loads(handle.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == STATUS_SUCCEEDED
    assert len(manifest["steps"]) == 2


def test_the_manifest_records_the_commit_the_run_was_produced_by(runner):
    """AD6: the run branch is cut from this sha, not from origin/main."""
    entry = RunEntry("noop", "Noop", "d", (("-m", "timeit", "-n", "1", "-r", "1", "pass"),))
    handle = runner.start(entry)
    runner.wait(timeout=60)
    manifest = json.loads(handle.manifest_path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["commit"])


def test_a_failing_first_step_leaves_the_second_unrun(runner):
    """Continuing past a failure produces a report tree that loads cleanly and
    means nothing."""
    entry = RunEntry(
        id="fails-first",
        name="Fails first",
        description="d",
        steps=(
            ("-m", "json.tool", "--no-such-flag"),
            ("-m", "timeit", "-n", "1", "-r", "1", "pass"),
        ),
    )
    runner.start(entry)
    runner.wait(timeout=60)

    status = runner.status()
    assert status["status"] == STATUS_FAILED
    assert status["steps"][0]["status"] == STATUS_FAILED
    assert status["steps"][0]["exit_code"] != 0
    assert status["steps"][1]["status"] == "skipped"
    assert status["steps"][1]["exit_code"] is None
    assert status["steps"][1]["started_at"] is None


def test_the_log_holds_the_child_output_and_a_banner_per_step(runner):
    entry = RunEntry("echo", "Echo", "d", (("-m", "json.tool", "--help"),))
    handle = runner.start(entry)
    runner.wait(timeout=60)

    text, offset = runner.read_log(handle.run_id)
    assert "=== step 1/1: python -u -m json.tool --help ===" in text
    assert "usage" in text.lower()
    assert offset == len(text.encode("utf-8"))

    # A second read from the returned offset yields nothing new.
    tail, next_offset = runner.read_log(handle.run_id, offset)
    assert tail == ""
    assert next_offset == offset


def test_read_log_returns_only_what_follows_the_offset(runner):
    entry = RunEntry("echo", "Echo", "d", (("-m", "json.tool", "--help"),))
    handle = runner.start(entry)
    runner.wait(timeout=60)

    head, offset = runner.read_log(handle.run_id, 0)
    assert offset > 10
    partial, _ = runner.read_log(handle.run_id, 10)
    assert head.endswith(partial)


def test_a_second_start_while_running_is_refused(runner):
    handle = runner.start(sleeping_entry())
    try:
        assert wait_for(lambda: runner.status()["status"] == STATUS_RUNNING)
        with pytest.raises(RunnerBusy, match=handle.run_id):
            runner.start(sleeping_entry())
    finally:
        runner.stop()
        runner.wait(timeout=60)


def test_stop_ends_the_run_as_stopped(runner):
    runner.start(sleeping_entry())
    assert wait_for(lambda: runner.status().get("steps", [{}])[0]["status"] == STATUS_RUNNING)
    runner.stop()
    runner.wait(timeout=60)

    status = runner.status()
    assert status["status"] == STATUS_STOPPED
    assert status["steps"][0]["status"] == STATUS_STOPPED


def test_status_is_idle_before_anything_has_run(runner):
    assert runner.status() == {"status": STATUS_IDLE, "run_id": None}


def test_a_state_file_naming_a_dead_pid_is_reported_interrupted(tmp_path):
    """AD8. A console that was killed leaves a state file claiming a run that no
    longer exists; adopting it would show a run progressing forever."""
    state_dir = tmp_path / "training_gui"
    state_dir.mkdir(parents=True)

    # A pid that is certainly not alive: spawn a trivial child and reap it.
    dead = subprocess.run([sys.executable, "-c", "pass"], check=True, capture_output=True)
    dead_pid = _reap_and_return_a_dead_pid()

    (state_dir / "state.json").write_text(
        json.dumps({"run_id": "20260101-000000-finetune", "pid": dead_pid, "status": "running"}),
        encoding="utf-8",
    )
    (state_dir / "20260101-000000-finetune.manifest.json").write_text(
        json.dumps(
            {
                "run_id": "20260101-000000-finetune",
                "entry_id": "finetune",
                "status": STATUS_RUNNING,
                "steps": [
                    {"index": 1, "status": STATUS_RUNNING},
                    {"index": 2, "status": "pending"},
                ],
            }
        ),
        encoding="utf-8",
    )
    assert dead.returncode == 0

    runner = Runner(repo_root=REPO_ROOT, state_dir=state_dir)
    status = runner.status()
    assert status["status"] == STATUS_INTERRUPTED
    assert status["steps"][0]["status"] == STATUS_INTERRUPTED
    assert status["steps"][1]["status"] == "skipped"

    # And it is written back, so the correction survives a restart.
    on_disk = json.loads(
        (state_dir / "20260101-000000-finetune.manifest.json").read_text(encoding="utf-8")
    )
    assert on_disk["status"] == STATUS_INTERRUPTED
    assert json.loads((state_dir / "state.json").read_text(encoding="utf-8"))["pid"] is None


def test_an_interrupted_state_does_not_wedge_the_console(tmp_path):
    """The reconciliation runs before the busy check, so a stale file left by a
    killed console does not refuse every subsequent run."""
    state_dir = tmp_path / "training_gui"
    state_dir.mkdir(parents=True)
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "run_id": "20260101-000000-x",
                "pid": _reap_and_return_a_dead_pid(),
                "status": "running",
            }
        ),
        encoding="utf-8",
    )
    (state_dir / "20260101-000000-x.manifest.json").write_text(
        json.dumps({"run_id": "20260101-000000-x", "status": STATUS_RUNNING, "steps": []}),
        encoding="utf-8",
    )

    runner = Runner(repo_root=REPO_ROOT, state_dir=state_dir)
    entry = RunEntry("noop", "Noop", "d", (("-m", "timeit", "-n", "1", "-r", "1", "pass"),))
    handle = runner.start(entry)
    runner.wait(timeout=60)
    assert runner.status()["run_id"] == handle.run_id
    assert runner.status()["status"] == STATUS_SUCCEEDED


def _reap_and_return_a_dead_pid() -> int:
    """A pid belonging to a child of this process that has exited and been
    reaped, so it is neither alive nor liable to be reused mid-test."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


def test_changed_paths_reads_git_status(runner):
    """Whatever the working tree currently holds, every reported path is under
    reports/ or models/ and carries a status letter."""
    for changed in runner.changed_paths():
        assert changed.path.startswith(("reports/", "models/")), changed.path
        assert changed.status
        assert changed.untracked == (changed.status == "??")


# ---------------------------------------------------------------------------
# AD1: the two requirements files must agree
# ---------------------------------------------------------------------------


def _pins(path: Path, packages: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if "==" not in line:
            continue
        name, _, version = line.partition("==")
        if name.strip() in packages:
            found[name.strip()] = version.strip()
    return found


def test_fastapi_and_uvicorn_pins_match():
    """The console runs in the ML environment (AD1), so that environment needs
    fastapi and uvicorn too. Drift between the two files would be discovered
    during a run rather than before one."""
    packages = {"fastapi", "uvicorn"}
    runtime = _pins(REPO_ROOT / "requirements.txt", packages)
    ml = _pins(REPO_ROOT / "requirements-ml.txt", packages)
    assert set(runtime) == packages, runtime
    assert ml == runtime


# ---------------------------------------------------------------------------
# git operations (Task 2)
#
# No network and no real repository mutation: the command runner is injected, so
# these assert on assembled argv and sequencing -- which is the whole risk in a
# module whose job is to issue a fixed list of commands in a fixed order.
# ---------------------------------------------------------------------------


BASE_SHA = "a" * 40


class FakeGit:
    """Records every argv and replies from a scripted table.

    ``responses`` maps a command prefix (as a tuple, e.g. ``("git", "push")``) to
    an ``(exit_code, output)`` pair. Anything unscripted succeeds silently, so a
    test only has to say what it is actually about.
    """

    def __init__(self, **responses):
        self.calls: list[list[str]] = []
        self.responses: dict[tuple[str, ...], tuple[int, str]] = {}
        for key, value in responses.items():
            self.responses[tuple(key.split("_"))] = value

    def __call__(self, argv):
        argv = list(argv)
        self.calls.append(argv)
        for length in range(len(argv), 0, -1):
            reply = self.responses.get(tuple(argv[:length]))
            if reply is not None:
                return reply
        return 0, ""

    @property
    def commands(self) -> list[str]:
        """``git fetch``-style labels, for readable sequencing assertions."""
        return [" ".join(call[:2]) for call in self.calls]

    def call(self, *prefix: str) -> list[str] | None:
        for argv in self.calls:
            if tuple(argv[: len(prefix)]) == prefix:
                return argv
        return None


def run_manifest(**overrides) -> dict:
    manifest = {
        "run_id": "20260831-120000-noise-2x2",
        "entry_id": "noise-2x2",
        "entry_name": "Noise sweep 2x2",
        "parameters": {"tree": "fever", "noise": "0.1"},
        "commit": BASE_SHA,
        "status": "succeeded",
        "started_at": "2026-08-31T12:00:00+00:00",
        "ended_at": "2026-08-31T13:00:00+00:00",
        "steps": [
            {
                "index": 1,
                "argv": ["-m", "scripts.encoder_training", "finetune"],
                "command": "python -u -m scripts.encoder_training finetune",
                "status": "succeeded",
                "exit_code": 0,
            }
        ],
    }
    manifest.update(overrides)
    return manifest


@pytest.fixture
def run_files(tmp_path):
    """A state dir holding a run's log and manifest, as Task 1's runner leaves it."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    run_id = run_manifest()["run_id"]
    (state_dir / f"{run_id}.log").write_text("output\n", encoding="utf-8")
    (state_dir / f"{run_id}.manifest.json").write_text(json.dumps(run_manifest()), encoding="utf-8")
    return state_dir


def save(tmp_path, run_files, git, manifest=None):
    return save_run_to_branch(
        manifest or run_manifest(),
        repo_root=tmp_path / "repo",
        state_dir=run_files,
        run_command=git,
    )


# -- the happy path ---------------------------------------------------------


def test_save_issues_the_fixed_sequence_in_order(tmp_path, run_files):
    """Two guards, then fetch, checkout, add, commit, push -- and only then the
    remote lookup that turns the branch into a compare link."""
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)
    git.responses[("git", "remote")] = (0, "git@github.com:ha08625-cloud/econsult.git")

    result = save(tmp_path, run_files, git)

    assert result.ok, result.message
    assert git.commands == [
        "git status",
        "git rev-parse",
        "git fetch",
        "git checkout",
        "git add",
        "git commit",
        "git push",
        "git remote",
    ]


def test_save_branches_from_the_manifest_sha_not_a_remote_branch(tmp_path, run_files):
    """AD6: the base is the commit the run was produced by."""
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)

    result = save(tmp_path, run_files, git)

    branch = "training/2026-08-31-20260831-120000-noise-2x2"
    assert result.branch == branch
    assert git.call("git", "checkout") == ["git", "checkout", "-b", branch, BASE_SHA]
    assert git.call("git", "push") == ["git", "push", "-u", "origin", branch]


def test_save_stages_only_the_two_prefixes_and_never_dash_a(tmp_path, run_files):
    """The assertion that keeps a stray file out of a run branch."""
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)

    save(tmp_path, run_files, git)

    assert git.call("git", "add") == ["git", "add", "--", "reports", "models"]
    for argv in git.calls:
        assert "-A" not in argv
        assert "--all" not in argv
        assert not {"merge", "rebase", "reset"} & set(argv)
        assert "--force" not in argv and "-f" not in argv
        assert "--amend" not in argv


def test_save_copies_the_log_and_manifest_into_the_reports_tree(tmp_path, run_files):
    """AD5: the branch carries the commands that produced the reports, not just
    the reports."""
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)

    save(tmp_path, run_files, git)

    run_id = run_manifest()["run_id"]
    destination = tmp_path / "repo" / "reports" / "training_runs" / run_id
    assert (destination / f"{run_id}.log").read_text(encoding="utf-8") == "output\n"
    assert (
        json.loads((destination / f"{run_id}.manifest.json").read_text(encoding="utf-8"))["run_id"]
        == run_id
    )


def test_commit_message_records_the_base_sha_parameters_and_steps(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)

    save(tmp_path, run_files, git)

    message = git.call("git", "commit")[3]
    assert message.splitlines()[0] == "training run: Noise sweep 2x2 (2026-08-31)"
    assert BASE_SHA in message
    assert "tree=fever" in message
    assert "python -u -m scripts.encoder_training finetune" in message
    assert "exit 0" in message


# -- failures stop the sequence ---------------------------------------------


def test_a_failed_fetch_stops_before_anything_mutating(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)
    git.responses[("git", "fetch")] = (128, "fatal: unable to access origin")

    result = save(tmp_path, run_files, git)

    assert not result.ok
    assert git.commands == ["git status", "git rev-parse", "git fetch"]
    assert "unable to access origin" in result.steps[-1].output


def test_a_failed_push_is_the_last_thing_attempted(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)
    git.responses[("git", "push")] = (1, "error: failed to push some refs")

    result = save(tmp_path, run_files, git)

    assert not result.ok
    assert git.commands[-1] == "git push"
    assert "error: failed to push some refs" in result.steps[-1].output
    # The remedy for the usual cause is in the message, not only in the raw error.
    assert BASE_SHA in result.message


def test_nothing_to_commit_is_reported_plainly_and_never_pushed(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, BASE_SHA)
    git.responses[("git", "commit")] = (1, "nothing to commit, working tree clean")

    result = save(tmp_path, run_files, git)

    assert not result.ok
    assert result.nothing_to_commit
    assert "changed nothing" in result.message
    assert "git push" not in git.commands


# -- guards ------------------------------------------------------------------


def test_a_dirty_path_outside_reports_blocks_the_whole_sequence(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "status")] = (0, " M app/services/triage.py\n?? reports/new.json\n")

    result = save(tmp_path, run_files, git)

    assert not result.ok
    assert result.blocking_paths == ("app/services/triage.py",)
    assert "app/services/triage.py" in result.message
    assert git.commands == ["git status"]


def test_a_head_that_moved_since_the_run_blocks_the_sequence(tmp_path, run_files):
    git = FakeGit()
    git.responses[("git", "rev-parse")] = (0, "b" * 40)

    result = save(tmp_path, run_files, git)

    assert not result.ok
    assert "moved since this run" in result.message
    assert git.commands == ["git status", "git rev-parse"]


def test_a_manifest_without_a_commit_cannot_be_saved(tmp_path, run_files):
    git = FakeGit()

    result = save(tmp_path, run_files, git, manifest=run_manifest(commit=None))

    assert not result.ok
    assert git.calls == []


def test_branch_name_requires_a_run_id():
    with pytest.raises(GitOpsError):
        branch_name({"started_at": "2026-08-31T12:00:00+00:00"})


def test_commit_message_survives_a_manifest_without_parameters():
    message = commit_message(run_manifest(parameters={}, steps=[]))
    assert message.startswith("training run: Noise sweep 2x2 (2026-08-31)")


# -- update from GitHub ------------------------------------------------------


def test_update_refuses_a_reports_only_dirty_tree_with_the_branch_message(tmp_path):
    git = FakeGit()
    git.responses[("git", "status")] = (0, "?? reports/encoder_training/2026-08-31-noise/\n")

    result = update_from_github(repo_root=tmp_path, run_command=git)

    assert not result.ok
    assert "Save this run to a branch first" in result.message
    assert git.commands == ["git status"]


def test_update_refuses_other_dirt_with_a_commit_or_stash_message(tmp_path):
    git = FakeGit()
    git.responses[("git", "status")] = (0, " M app/main.py\n")

    result = update_from_github(repo_root=tmp_path, run_command=git)

    assert not result.ok
    assert "Commit or stash" in result.message


def test_update_fetches_then_pulls_ff_only_on_a_clean_tree(tmp_path):
    git = FakeGit()
    git.responses[("git", "pull")] = (0, "Fast-forward")

    result = update_from_github(repo_root=tmp_path, run_command=git)

    assert result.ok
    assert git.commands == ["git status", "git fetch", "git pull"]
    assert git.call("git", "pull") == ["git", "pull", "--ff-only"]


def test_update_stops_when_the_fetch_fails(tmp_path):
    git = FakeGit()
    git.responses[("git", "fetch")] = (1, "fatal: could not read from remote")

    result = update_from_github(repo_root=tmp_path, run_command=git)

    assert not result.ok
    assert git.commands == ["git status", "git fetch"]


# -- compare url -------------------------------------------------------------


@pytest.mark.parametrize(
    "remote",
    [
        "git@github.com:ha08625-cloud/econsult.git",
        "https://github.com/ha08625-cloud/econsult.git",
        "https://github.com/ha08625-cloud/econsult",
    ],
)
def test_compare_url_handles_both_remote_forms(remote):
    assert compare_url(remote, "training/2026-08-31-run") == (
        "https://github.com/ha08625-cloud/econsult/compare/training/2026-08-31-run?expand=1"
    )


@pytest.mark.parametrize(
    "remote",
    ["git@gitlab.com:owner/repo.git", "/srv/mirrors/econsult.git", ""],
)
def test_compare_url_returns_none_rather_than_guessing(remote):
    assert compare_url(remote, "training/x") is None
