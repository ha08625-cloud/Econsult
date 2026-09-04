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
    GitResult,
    GitStep,
    _porcelain_paths,
    branch_name,
    commit_message,
    compare_url,
    default_runner,
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
    ChangedPath,
    RunHandle,
    Runner,
    RunnerBusy,
    RunnerError,
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
        # The composites come first: they are the buttons that get pressed,
        # and everything below them is an escape hatch for when one of their
        # steps has to be repeated on its own.
        "decl-sweep-2x2",
        "decl-sweep-register",
        "lexical-expansion-2x2",
        "smoke-cuda",
        "train-canary",
        "score-companions",
        "generate-folds",
        "merge-folds",
        "decl-generate-folds-all",
        "decl-compare-2x2",
        "decl-compare-register",
    ]


# ---------------------------------------------------------------------------
# The lexical variant expansion composite (plan Task 6, DD12)
# ---------------------------------------------------------------------------

LEXICAL = "lexical-expansion-2x2"


def _lexical() -> object:
    return {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}[LEXICAL]


def _value(step, flag: str) -> str | None:
    return step[step.index(flag) + 1] if flag in step else None


def _training_steps(entry):
    return [step for step in entry.steps if "finetune" in step]


def test_the_lexical_cells_point_at_exactly_the_two_trees_the_run_writes():
    """The guard that matters, and the reason the entry is worth committing.

    The four cells differ only in which of two trees ``--data-dir`` and
    ``--test-dir`` name, and both are literals typed out cell by cell. A path
    mistyped in one place and not another produces a run that trains for forty
    minutes and then compares a tree against itself -- which does not fail, and
    reads as "expansion changed nothing" in the report. Set equality here catches
    it in under a second, before any GPU time.
    """
    entry = _lexical()
    generated = {
        _value(step, "--out-dir")
        for step in entry.steps
        if "generate-folds" in step or ("--in-dir" in step and "--out-dir" in step)
    }
    assert len(generated) == 2, generated

    trained = _training_steps(entry)
    assert len(trained) == 4, len(trained)
    assert {_value(step, "--data-dir") for step in trained} == generated
    assert {_value(step, "--test-dir") for step in trained} == generated
    # And all four combinations, once each: three cells and a repeat is a 2x2
    # with a hole in it, and the hole would be invisible in the report.
    assert len({(_value(s, "--data-dir"), _value(s, "--test-dir")) for s in trained}) == 4


def test_the_lexical_run_expands_the_tree_it_generated():
    """``expand.py`` reads ``--in-dir`` and writes ``--out-dir``. Expanding some
    other tree than the one just generated would give the two arms different
    provenance, which is the one thing the post-processing architecture exists
    to rule out."""
    entry = _lexical()
    generated = _value(next(step for step in entry.steps if "generate-folds" in step), "--out-dir")
    expand = next(step for step in entry.steps if "--in-dir" in step)
    assert _value(expand, "--in-dir") == generated
    assert _value(expand, "--out-dir") != generated


def test_the_lexical_run_starts_with_the_smoke_test():
    """Ten seconds, and it fails immediately on a broken driver rather than
    forty minutes in."""
    assert _lexical().steps[0] == ("-m", "scripts.encoder_training", "smoke-cuda")


def test_the_lexical_run_checks_the_rules_before_it_spends_any_gpu():
    """``--dry-run-lint`` writes nothing and takes seconds, and it fails the run
    if the rule file has drifted since it was validated. Putting a guard *inside*
    the sequence is the point of having a sequence -- after the last training
    step it would only tell you what the forty minutes had been spent on."""
    entry = _lexical()
    positions = [index for index, step in enumerate(entry.steps) if "--dry-run-lint" in step]
    assert len(positions) == 1
    assert positions[0] < min(index for index, step in enumerate(entry.steps) if "finetune" in step)


def test_every_lexical_cell_writes_to_its_own_directories():
    """Four cells sharing a report directory would overwrite each other's
    ``fever_present.arm_b_finetune.json`` and leave one report where four
    should be -- and the guard reads two of them by path."""
    trained = _training_steps(_lexical())
    for flag in ("--report-dir", "--models-dir", "--predictions"):
        written = [_value(step, flag) for step in trained]
        assert all(written), flag
        assert len(set(written)) == len(trained), flag


def test_the_paired_flip_step_reads_the_files_the_cells_wrote():
    """The pairing is by path, and a path that names a cell which never ran is
    the failure mode a composite is supposed to remove."""
    entry = _lexical()
    written = {_value(step, "--predictions") for step in _training_steps(entry)}
    flip = next(step for step in entry.steps if "paired-flip-rate" in step)
    read = {
        element
        for element in flip
        if isinstance(element, str) and element.endswith(".predictions.json")
    }
    assert read == written
    # Two arms, three tokens each: a flip rate is computed within an arm and
    # never across two.
    assert sum(1 for element in flip if element == "--arm") == 2


def test_the_lexical_guard_is_scored_on_the_clean_test_tree_for_both_arms():
    """DD7. The two arms are only comparable where they were scored on identical
    text, which is the clean test tree; a guard read off the expanded-test cells
    would compare two different test sets and mean nothing."""
    entry = _lexical()
    flip = next(step for step in entry.steps if "paired-flip-rate" in step)
    clean_dir = _value(flip, "--clean-dir")
    clean_test_report_dirs = {
        _value(step, "--report-dir")
        for step in _training_steps(entry)
        if _value(step, "--test-dir") == clean_dir
    }
    assert len(clean_test_report_dirs) == 2

    guards = {_value(flip, "--guard-baseline"), _value(flip, "--guard-arm")}
    assert len(guards) == 2
    for guard in guards:
        assert any(guard.startswith(f"{directory}/") for directory in clean_test_report_dirs), guard

    # The bound is a literal in the entry rather than a default picked up
    # silently: a guard whose bound is invisible in the committed command is not
    # pre-registered in any useful sense.
    assert _value(flip, "--guard-bound")


def test_every_declarative_cell_writes_to_its_own_directories():
    """The failure this prevents is silent and expensive.

    Every declarative entry writes under a path built from both shares, so a
    second cell cannot land on the first's fold tree, report tree or models. The
    committed ``generate-folds`` entry takes the default directories, which is
    fine while there is one arm and wrong the moment there are two: the second
    run would overwrite the first and the comparison would be a tree against
    itself.
    """
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    cells = [
        {"companion_share": companion, "declarative_share": declarative}
        for companion in ("0.0", "0.5")
        for declarative in ("0.0", "0.3", "0.6")
    ]

    for entry_id in ("decl-generate-folds-all",):
        seen: set[str] = set()
        for values in cells:
            steps = resolve(entries[entry_id], values)
            directories = {
                step[position + 1]
                for step in steps
                for position, element in enumerate(step)
                if element in ("--out-dir", "--data-dir", "--report-dir", "--models-dir")
            }
            assert directories, entry_id
            assert not directories & seen, f"{entry_id} reuses a directory across cells"
            seen |= directories


def test_the_comparison_entries_point_at_directories_the_sweep_produces():
    """The one coupling the catalogue cannot check for itself.

    The comparison entries name their cells as literal paths, because the
    console has no way to pass a list; the generate entries build the same paths
    by substitution. Change the template in one place and the comparison points
    at directories nothing writes -- which surfaces an hour in, as a run that
    refuses because a cell does not exist, after the four hours of training that
    produced the cells it cannot find.
    """
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}

    produced = set()
    for values in (
        {"companion_share": companion, "declarative_share": declarative}
        for companion in ("0.0", "0.5")
        for declarative in ("0.0", "0.3", "0.6")
    ):
        for step in resolve(entries["decl-generate-folds-all"], values):
            produced.add(step[step.index("--out-dir") + 1])

    for entry_id in ("decl-compare-2x2", "decl-compare-register"):
        for step in entries[entry_id].steps:
            cells = [step[i + 1] for i, element in enumerate(step) if element == "--cell"]
            assert len(cells) >= 2, entry_id
            assert len(set(cells)) == len(cells), f"{entry_id} repeats a cell"
            unknown = sorted(set(cells) - produced)
            assert not unknown, f"{entry_id} names cells the sweep never writes: {unknown}"


def test_the_declarative_sweep_scores_the_real_text_holdout():
    """``--no-holdout`` here would produce a comparison that cannot answer the
    question the arms exist for, and the report would say the check was skipped
    in a line nobody reads. The holdout is on by default, so this asserts the
    absence of the flag rather than its presence."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in (
        "decl-compare-2x2",
        "decl-compare-register",
        "decl-sweep-2x2",
        "decl-sweep-register",
    ):
        for step in entries[entry_id].steps:
            if step[2] != "declarative-compare":
                # The composites carry a canary that skips the holdout on purpose;
                # the assertion is about the step that produces the numbers.
                continue
            assert "--no-holdout" not in step, entry_id


def test_the_canary_skips_the_holdout_deliberately():
    """The comparisons load and validate the holdout before any GPU work, so a
    canary that scored it would spend time re-checking something already checked
    and prove nothing more about the training path."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in ("train-canary", *COMPOSITES):
        train = [step for step in entries[entry_id].steps if step[2] == "finetune"]
        assert len(train) == 1, entry_id
        assert "--no-holdout" in train[0], entry_id


def test_the_declarative_sweep_covers_the_six_trainable_signals():
    """Not seven. ``recent_uti_present`` is excluded by DD9 -- its label turns on
    a 30-day window and six written policy rules -- and it has no trained head
    either, so including it would produce a run that fails partway."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in ("decl-generate-folds-all",):
        entry = entries[entry_id]
        signals = [step[step.index("--signal") + 1] for step in entry.steps]
        assert len(signals) == 6, entry_id
        assert "recent_uti_present" not in signals, entry_id
        assert len(set(signals)) == 6, entry_id

    # The composites cover the same six, once per cell they compare: four cells
    # for the 2x2 and three for the register arm. Only the steps that write a
    # declarative cell count -- the canary also names a signal, and it is not
    # part of the sweep's coverage.
    for entry_id, cells in (("decl-sweep-2x2", 4), ("decl-sweep-register", 3)):
        entry = entries[entry_id]
        signals = [
            step[step.index("--signal") + 1]
            for step in entry.steps
            if _writes_a_declarative_cell(step)
        ]
        assert len(signals) == 6 * cells, entry_id
        assert set(signals) == {
            "fever_present",
            "dysuria_present",
            "flank_pain_present",
            "haematuria_present",
            "nocturia_present",
            "urinary_frequency_present",
        }, entry_id
        assert "recent_uti_present" not in signals, entry_id


def test_the_committed_catalogue_names_the_base_model_explicitly():
    """The flag is baked in even though ``DEFAULT_BASE_MODEL`` already agrees
    with it, so the encoder is visible in the command the console shows and in
    its log rather than being something a reader reconstructs from a default."""
    compare = next(e for e in load_catalogue(DEFAULT_CATALOGUE_PATH) if e.id == "decl-compare-2x2")
    step = compare.steps[0]
    assert "--base-model" in step
    # A literal, not a parameter: a retired encoder picked by accident is how a
    # run silently stops being comparable with the committed reports.
    assert step[step.index("--base-model") + 1] == "roberta-base"


COMPOSITES = ("decl-sweep-2x2", "decl-sweep-register")

#: Where the declarative sweep's cells live. The canary writes its own one-fold
#: tree outside this prefix, so the assertions about cells can ignore it without
#: losing any of their teeth.
DECL_CELL_PREFIX = "data/synthetic/generated/decl/"


CANARY_TREE = "data/synthetic/generated/canary"


def _touches_the_canary_tree(step) -> bool:
    return CANARY_TREE in step


def _writes_a_declarative_cell(step) -> bool:
    return "--out-dir" in step and step[step.index("--out-dir") + 1].startswith(DECL_CELL_PREFIX)


def test_each_composite_generates_exactly_the_cells_it_compares():
    """The guard that pays for itself in GPU hours.

    A composite writes its cells with ``--out-dir`` and then compares them by
    ``--cell``, and both are literals typed out cell by cell. A share mistyped in
    one place and not the other -- ``d0.3`` where the comparison says ``d0.6`` --
    produces a run that generates three of the cells it needs, spends 25 minutes
    doing it, and then refuses at the start of the four-hour comparison, or worse
    finds a stale tree there and compares against the wrong data. Set equality
    here catches that in under a second.
    """
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in COMPOSITES:
        entry = entries[entry_id]
        generated = {
            step[step.index("--out-dir") + 1]
            for step in entry.steps
            if _writes_a_declarative_cell(step)
        }
        compared = {
            step[position + 1]
            for step in entry.steps
            for position, element in enumerate(step)
            if element == "--cell"
        }
        assert generated, entry_id
        assert generated == compared, entry_id


def test_the_canary_agrees_with_itself_about_the_fold_count():
    """The coupling that makes the canary work at all.

    ``load_folds`` refuses a tree whose sidecar records a different fold count
    from the one being requested, so a canary that generated one fold and then
    trained against five -- or the reverse -- would fail in the loader every
    time, and the failure would read as a broken environment rather than a
    broken catalogue entry. That is the worst possible error from a canary: the
    thing whose job is to tell you the machine is fine would tell you it is not.
    """
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in ("train-canary", *COMPOSITES):
        canary = [step for step in entries[entry_id].steps if _touches_the_canary_tree(step)]
        assert len(canary) == 2, entry_id
        folds = {step[step.index("--folds") + 1] for step in canary}
        assert folds == {"1"}, entry_id


def test_the_canary_never_touches_a_directory_a_sweep_reads():
    """It writes its own fold tree, reports and models. A canary that wrote into
    a cell would corrupt the comparison it is supposed to be protecting -- and a
    one-fold tree landing in a five-fold cell is exactly the half-written tree
    that makes a presence check unsafe."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in ("train-canary", *COMPOSITES):
        for step in entries[entry_id].steps:
            if not _touches_the_canary_tree(step):
                continue
            written = {
                step[position + 1]
                for position, element in enumerate(step)
                if element in ("--out-dir", "--data-dir", "--report-dir", "--models-dir")
            }
            assert written, entry_id
            for directory in written:
                assert not directory.startswith(DECL_CELL_PREFIX), (entry_id, directory)
                assert "canary" in directory, (entry_id, directory)


def test_each_composite_runs_the_canary_before_it_generates_anything():
    """Three minutes in rather than twenty-six. The point of the canary's
    position is that a machine which cannot run a backward pass fails before the
    25 minutes of CPU generation, not after them."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in COMPOSITES:
        steps = entries[entry_id].steps
        assert _touches_the_canary_tree(steps[1]), entry_id
        assert steps[2][2] == "finetune", entry_id
        first_cell = next(
            position for position, step in enumerate(steps) if _writes_a_declarative_cell(step)
        )
        assert first_cell > 2, entry_id


def test_each_composite_starts_with_the_smoke_test():
    """Ten seconds at the front, so a broken driver or wheel fails now rather
    than after the 25 minutes of generation that precede the first GPU work."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in COMPOSITES:
        assert entries[entry_id].steps[0] == ("-m", "scripts.encoder_training", "smoke-cuda")


def test_the_composites_take_no_parameters():
    """The one-button entries are entirely literal: with no parameters declared,
    no browser-supplied string reaches their argv at all, not even one matched
    against a committed choice."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in COMPOSITES:
        assert entries[entry_id].parameters == ()


def test_score_companions_reads_a_directory_the_comparisons_write():
    """``score-companions`` used to pass no ``--report-dir`` and so read the CLI
    default, which no declarative comparison ever writes to -- the button could
    not score the runs the console performs. Every choice it now offers must be a
    directory some comparison entry actually writes."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    written = {
        step[step.index("--report-dir") + 1]
        for entry_id in ("decl-compare-2x2", "decl-compare-register")
        for step in entries[entry_id].steps
        if "--report-dir" in step
    }
    report_dir = entries["score-companions"].parameter("report_dir")
    assert report_dir is not None
    assert set(report_dir.choices) <= written
    assert report_dir.default in written


def test_the_composites_score_the_comparison_they_just_ran():
    """The final step reads back the directory the composite's own comparison
    wrote, so the run ends with the scorecard in the log instead of needing a
    second button press against a directory chosen from memory."""
    entries = {entry.id: entry for entry in load_catalogue(DEFAULT_CATALOGUE_PATH)}
    for entry_id in COMPOSITES:
        steps = entries[entry_id].steps
        assert steps[-1][2] == "score-companions", entry_id
        scored = steps[-1][steps[-1].index("--report-dir") + 1]
        compared = steps[-2][steps[-2].index("--report-dir") + 1]
        assert scored == compared, entry_id


def test_every_multi_step_entry_labels_its_steps():
    """A run of twenty-seven steps is unreadable as a list of command lines. The
    labels are display only, so this asserts they exist and are one per step;
    ``load_catalogue`` has already rejected a list of the wrong length."""
    for entry in load_catalogue(DEFAULT_CATALOGUE_PATH):
        if len(entry.steps) > 1:
            assert len(entry.step_labels) == len(entry.steps), entry.id


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


def test_step_labels_of_the_wrong_length_are_rejected(tmp_path):
    """Labels that have drifted out of step with the steps name the wrong rows,
    which is worse than no labels at all."""
    path = write_catalogue(
        tmp_path / "runs.json",
        minimal_run(step_labels=["Smoke test", "One too many"]),
    )
    with pytest.raises(CatalogueError, match="step_labels"):
        load_catalogue(path)


def test_step_labels_that_are_not_a_list_are_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(step_labels="Smoke test"))
    with pytest.raises(CatalogueError, match="step_labels"):
        load_catalogue(path)


def test_an_empty_step_label_is_rejected(tmp_path):
    path = write_catalogue(tmp_path / "runs.json", minimal_run(step_labels=["   "]))
    with pytest.raises(CatalogueError, match="step_labels"):
        load_catalogue(path)


def test_absent_step_labels_are_an_empty_tuple(tmp_path):
    """The field is optional: an entry without it renders by step index."""
    path = write_catalogue(tmp_path / "runs.json", minimal_run())
    assert load_catalogue(path)[0].step_labels == ()


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


def test_a_modified_file_keeps_its_first_character(tmp_path):
    """``git status --porcelain`` puts the status in the first two columns, so a
    modified-not-staged line begins with a space. Trimming it upstream shifted
    every path left by one, which named ``eports/x`` in a guard message and put a
    reports-only dirty tree on the wrong branch of the update message."""
    git = FakeGit()
    git.responses[("git", "status")] = (0, "M reports/encoder_training/2026-08-31/summary.json")

    result = update_from_github(repo_root=tmp_path, run_command=git)

    assert result.blocking_paths == ("reports/encoder_training/2026-08-31/summary.json",)
    assert "Save this run to a branch first" in result.message


def test_the_real_git_runner_does_not_trim_the_porcelain_status_column(tmp_path):
    """The same bug at its source: a runner that ``strip()``s its output eats the
    leading column. Against a real repository, because that is the only place the
    leading space actually exists."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@example.com"],
        ["git", "config", "user.name", "t"],
    ):
        subprocess.run(argv, cwd=repo, check=True, capture_output=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "first"], cwd=repo, check=True, capture_output=True)
    tracked.write_text("two\n", encoding="utf-8")

    exit_code, output = default_runner(repo)(["git", "status", "--porcelain"])

    assert exit_code == 0
    assert output.startswith(" M ")
    assert list(_porcelain_paths(output)) == ["tracked.txt"]


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


# ---------------------------------------------------------------------------
# the HTTP layer
#
# TestClient against fakes: no subprocess, no repository, no network. What is
# actually being tested here is the boundary DD4 describes -- that an id and a
# set of enumerated strings are the only things a request can influence -- so the
# id and parameter rejections are asserted at this layer as well as in the
# catalogue, and each one also asserts the runner was never reached.
# ---------------------------------------------------------------------------


try:
    from fastapi.testclient import TestClient

    from scripts.training_gui.server import GitOps, create_app
except ImportError:  # pragma: no cover - a machine without the console's deps
    TestClient = None
    GitOps = None
    create_app = None

requires_fastapi = pytest.mark.skipif(
    TestClient is None, reason="fastapi and httpx are needed for the HTTP tests"
)


class FakeRunner:
    """Mirrors the real runner's surface, resolving argv exactly as it does.

    ``start`` running the catalogue's own ``resolve`` is the point: the argv the
    fake records is the argv a real run would execute, so an assertion about what
    the runner received is an assertion about what would have run.
    """

    def __init__(self, manifest=None):
        self.manifest = manifest or {"status": STATUS_IDLE, "run_id": None}
        self.started = []
        self.argvs = None
        self.busy = False
        self.stopped = False
        self.log_reads = []
        self.changed = ()

    def start(self, entry, values):
        if self.busy:
            raise RunnerBusy("run 20260831-120000-finetune is already running")
        self.started.append((entry.id, dict(values)))
        self.argvs = [list(argv) for argv in resolve(entry, values)]
        return RunHandle(
            run_id="20260831-120000-" + entry.id,
            entry_id=entry.id,
            log_path=Path("log"),
            manifest_path=Path("manifest"),
        )

    def stop(self):
        if not self.busy:
            raise RunnerError("no run is active")
        self.stopped = True

    def status(self):
        return self.manifest

    def read_log(self, run_id, offset=0):
        self.log_reads.append((run_id, offset))
        return "tail\n", offset + 5

    def changed_paths(self):
        return self.changed


class FakeGitOps:
    def __init__(self, save_result=None, update_result=None):
        self.save_result = save_result or GitResult(ok=True, message="Saved.")
        self.update_result = update_result or GitResult(ok=True, message="Already up to date.")
        self.saved = []
        self.updated = 0

    def save_run_to_branch(self, manifest):
        self.saved.append(manifest)
        return self.save_result

    def update_from_github(self):
        self.updated += 1
        return self.update_result


def client_for(runner=None, git=None, catalogue=None):
    runner = runner or FakeRunner()
    git = git or FakeGitOps()
    app = create_app(runner, catalogue or load_catalogue(), git)
    return TestClient(app), runner, git


@requires_fastapi
def test_the_catalogue_endpoint_returns_every_committed_entry():
    client, _, _ = client_for()

    body = client.get("/api/catalogue").json()

    committed = load_catalogue()
    assert [entry["id"] for entry in body["runs"]] == [entry.id for entry in committed]
    generate = next(entry for entry in body["runs"] if entry["id"] == "generate-folds")
    assert [parameter["name"] for parameter in generate["parameters"]] == ["signal"]
    assert generate["parameters"][0]["default"] == "fever_present"
    # The command line shown before the click is the one that would run.
    assert generate["commands"] == [
        "python -u -m scripts.encoder_training generate-folds --folds 5 --signal fever_present"
    ]
    # The labels travel with the multi-step entries, so the page can render a
    # checklist rather than twenty-seven command lines.
    sweep = next(entry for entry in body["runs"] if entry["id"] == "decl-sweep-2x2")
    assert len(sweep["step_labels"]) == len(sweep["steps"])
    assert sweep["step_labels"][0] == "CUDA smoke test"
    assert generate["step_labels"] == []


@requires_fastapi
def test_an_unknown_id_is_a_404_and_never_reaches_the_runner():
    client, runner, _ = client_for()

    response = client.post("/api/run", json={"id": "rm-rf", "parameters": {}})

    assert response.status_code == 404
    assert runner.started == []


@requires_fastapi
def test_a_parameter_outside_the_choices_is_a_400_and_never_reaches_the_runner():
    client, runner, _ = client_for()

    response = client.post(
        "/api/run",
        json={"id": "generate-folds", "parameters": {"signal": "fever_present; rm -rf /"}},
    )

    assert response.status_code == 400
    assert runner.started == []


@requires_fastapi
def test_a_parameter_naming_nothing_declared_is_a_400():
    client, runner, _ = client_for()

    response = client.post(
        "/api/run", json={"id": "generate-folds", "parameters": {"output_dir": "/etc"}}
    )

    assert response.status_code == 400
    assert runner.started == []


@requires_fastapi
def test_a_non_string_parameter_value_is_a_400():
    client, runner, _ = client_for()

    response = client.post("/api/run", json={"id": "generate-folds", "parameters": {"signal": 7}})

    assert response.status_code == 400
    assert runner.started == []


@requires_fastapi
def test_a_valid_body_starts_the_run_and_hands_the_runner_the_resolved_argv():
    client, runner, _ = client_for()

    response = client.post(
        "/api/run",
        json={
            "id": "generate-folds",
            "parameters": {"signal": "dysuria_present"},
        },
    )

    assert response.status_code == 202
    assert runner.argvs == [
        [
            "-m",
            "scripts.encoder_training",
            "generate-folds",
            "--folds",
            "5",
            "--signal",
            "dysuria_present",
        ]
    ]
    assert response.json()["run_id"] == "20260831-120000-generate-folds"


@requires_fastapi
def test_an_omitted_parameter_takes_its_declared_default():
    client, runner, _ = client_for()

    client.post("/api/run", json={"id": "generate-folds", "parameters": {}})

    assert "--signal" in runner.argvs[0]
    assert runner.argvs[0][runner.argvs[0].index("--signal") + 1] == "fever_present"


@requires_fastapi
def test_starting_a_second_run_while_one_is_active_is_a_409():
    runner = FakeRunner()
    runner.busy = True
    client, _, _ = client_for(runner=runner)

    response = client.post("/api/run", json={"id": "smoke-cuda", "parameters": {}})

    assert response.status_code == 409


@requires_fastapi
def test_status_reports_the_step_number_and_the_current_command():
    manifest = {
        "run_id": "20260831-120000-finetune",
        "entry_name": "Arm B: fine-tune one signal",
        "status": STATUS_RUNNING,
        "steps": [
            {"index": 1, "command": "python -u -m a", "status": STATUS_SUCCEEDED, "exit_code": 0},
            {"index": 2, "command": "python -u -m b", "status": STATUS_RUNNING, "exit_code": None},
            {"index": 3, "command": "python -u -m c", "status": "pending", "exit_code": None},
        ],
    }
    client, _, _ = client_for(runner=FakeRunner(manifest))

    body = client.get("/api/status").json()

    assert body["status"] == STATUS_RUNNING
    assert (body["step_index"], body["step_count"]) == (2, 3)
    assert body["command"] == "python -u -m b"


@requires_fastapi
def test_status_carries_the_entrys_step_labels_so_the_page_can_name_each_step():
    """The labels belong to the catalogue, not to the run, so the status endpoint
    joins them on by ``entry_id``. A run of an entry the catalogue no longer has
    gets an empty list rather than an error: the page falls back to step numbers."""
    manifest = {
        "run_id": "20260902-120000-decl-sweep-2x2",
        "entry_id": "decl-sweep-2x2",
        "status": STATUS_RUNNING,
        "steps": [{"index": 1, "command": "python -u -m a", "status": STATUS_RUNNING}],
    }
    client, _, _ = client_for(runner=FakeRunner(manifest))

    body = client.get("/api/status").json()

    entry = next(item for item in load_catalogue() if item.id == "decl-sweep-2x2")
    assert body["step_labels"] == list(entry.step_labels)
    assert body["step_labels"][0] == "CUDA smoke test"


@requires_fastapi
def test_status_of_an_unlabelled_or_unknown_entry_carries_no_labels():
    client, _, _ = client_for(
        runner=FakeRunner({"run_id": "20260902-120000-gone", "entry_id": "no-such-entry"})
    )

    assert client.get("/api/status").json()["step_labels"] == []


@requires_fastapi
def test_status_is_idle_with_no_run():
    client, _, _ = client_for()

    body = client.get("/api/status").json()

    assert body["status"] == STATUS_IDLE
    assert body["step_index"] is None


@requires_fastapi
def test_the_log_endpoint_passes_the_offset_through_and_returns_the_next_one():
    runner = FakeRunner({"run_id": "20260831-120000-finetune", "status": STATUS_RUNNING})
    client, _, _ = client_for(runner=runner)

    body = client.get("/api/log", params={"offset": 120}).json()

    assert runner.log_reads == [("20260831-120000-finetune", 120)]
    assert body == {"text": "tail\n", "next_offset": 125, "run_id": "20260831-120000-finetune"}


@requires_fastapi
def test_the_log_endpoint_is_empty_rather_than_an_error_before_any_run():
    client, _, _ = client_for()

    assert client.get("/api/log?offset=0").json() == {
        "text": "",
        "next_offset": 0,
        "run_id": None,
    }


@requires_fastapi
def test_stopping_with_nothing_running_is_a_409():
    client, runner, _ = client_for()

    response = client.post("/api/stop")

    assert response.status_code == 409
    assert not runner.stopped


@requires_fastapi
def test_stopping_an_active_run_reaches_the_runner():
    runner = FakeRunner()
    runner.busy = True
    client, _, _ = client_for(runner=runner)

    assert client.post("/api/stop").status_code == 200
    assert runner.stopped


@requires_fastapi
def test_changes_lists_what_the_run_wrote():
    runner = FakeRunner()
    runner.changed = (
        ChangedPath(path="reports/encoder_training/2026-08-31-noise/summary.json", status="??"),
        ChangedPath(path="models/fever_present/config.json", status="M"),
    )
    client, _, _ = client_for(runner=runner)

    body = client.get("/api/changes").json()

    assert [item["path"] for item in body["changed"]] == [
        "reports/encoder_training/2026-08-31-noise/summary.json",
        "models/fever_present/config.json",
    ]
    assert body["changed"][0]["untracked"] is True
    assert body["changed"][1]["untracked"] is False


@requires_fastapi
def test_save_branch_hands_the_manifest_over_and_returns_the_branch():
    manifest = run_manifest()
    git = FakeGitOps(
        save_result=GitResult(
            ok=True,
            message="Saved to branch training/2026-08-31-x.",
            branch="training/2026-08-31-x",
            compare_url="https://github.com/o/r/compare/training/2026-08-31-x?expand=1",
        )
    )
    client, _, _ = client_for(runner=FakeRunner(manifest), git=git)

    body = client.post("/api/save-branch").json()

    assert git.saved == [manifest]
    assert body["ok"] is True
    assert body["branch"] == "training/2026-08-31-x"
    assert body["compare_url"].endswith("?expand=1")


@requires_fastapi
def test_save_branch_surfaces_the_failed_step_raw_and_invents_no_success():
    git = FakeGitOps(
        save_result=GitResult(
            ok=False,
            message="git push failed.",
            steps=[
                GitStep(argv=("git", "fetch", "origin"), exit_code=0, output=""),
                GitStep(
                    argv=("git", "push", "-u", "origin", "training/x"),
                    exit_code=128,
                    output="error: failed to push some refs",
                ),
            ],
            branch="training/x",
        )
    )
    client, _, _ = client_for(runner=FakeRunner(run_manifest()), git=git)

    body = client.post("/api/save-branch").json()

    assert body["ok"] is False
    failed = [step for step in body["steps"] if step["exit_code"] != 0]
    assert failed[-1]["output"] == "error: failed to push some refs"
    assert failed[-1]["argv"] == ["git", "push", "-u", "origin", "training/x"]


@requires_fastapi
def test_save_branch_with_no_run_is_a_409():
    client, _, git = client_for()

    assert client.post("/api/save-branch").status_code == 409
    assert git.saved == []


@requires_fastapi
def test_save_branch_while_the_run_is_still_going_is_a_409():
    manifest = run_manifest(status=STATUS_RUNNING)
    client, _, git = client_for(runner=FakeRunner(manifest))

    assert client.post("/api/save-branch").status_code == 409
    assert git.saved == []


@requires_fastapi
def test_update_carries_no_payload_and_returns_the_result():
    git = FakeGitOps(update_result=GitResult(ok=False, message="git fetch origin failed."))
    client, _, _ = client_for(git=git)

    body = client.post("/api/update").json()

    assert git.updated == 1
    assert body == {
        "ok": False,
        "message": "git fetch origin failed.",
        "steps": [],
        "branch": None,
        "compare_url": None,
        "nothing_to_commit": False,
        "blocking_paths": [],
    }


@requires_fastapi
def test_the_page_is_served_at_the_root():
    client, _, _ = client_for()

    response = client.get("/")

    assert response.status_code == 200
    assert "Encoder training console" in response.text


@requires_fastapi
def test_no_endpoint_takes_a_path_or_a_branch_name_from_the_browser():
    """DD4 as a property of the app: the only body field any endpoint reads
    besides ``id`` is ``parameters``, and the git routes read nothing at all."""
    client, runner, git = client_for()

    client.post("/api/update", json={"branch": "main", "force": True})
    client.post("/api/save-branch", json={"branch": "../../etc"})

    assert git.updated == 1
    assert git.saved == []
