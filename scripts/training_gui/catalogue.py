"""The run catalogue: what the console is allowed to run, and with what.

The catalogue is a JSON file checked into the repository. It is the whole of the
console's authority: the browser sends an entry id and, per declared parameter,
one string, and every string that can ever reach a command line is a literal
already present in ``runs.json``. There is no code path from a request body to an
argv element that is not an exact match against a committed list of choices.

Two rules do most of the work.

**Vectors are module invocations, never interpreters.** Every step's first
element must be exactly ``-m``; the runner builds the real command as
``[sys.executable, "-u", *argv]``. Naming an interpreter in the catalogue would
let a run execute against whichever Python happened to be on PATH, and on this
project that failure does not look like a configuration error -- it surfaces as a
``SyntaxError`` in ``scripts/synthetic_data/recombine.py`` (3.12 syntax under
3.11) or as a missing-torch traceback. Requiring ``-m`` excludes ``python``,
``python3``, an absolute interpreter path and ``git`` mechanically. Git is
``gitops.py``'s business and is not in the catalogue.

**Parameters are enumerated, never free text.** A declaration carries a name, a
label, an explicit list of allowed choices and a default drawn from them; the
page renders a dropdown. No numeric fields, because a numeric field is free text
plus a validator and the validator is where this would go wrong.
"""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The catalogue that ships with the console.
DEFAULT_CATALOGUE_PATH = Path(__file__).resolve().parent / "runs.json"

_ID_PATTERN = re.compile(r"^[a-z0-9-]+$")
_PARAMETER_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

#: ``{name}`` placeholders inside a step element. Deliberately narrow: it matches
#: the same shape as a parameter name, so a stray brace in an argument is a
#: catalogue error rather than a silent non-substitution.
_PLACEHOLDER_PATTERN = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class CatalogueError(Exception):
    """A catalogue is malformed, or a request does not match one."""


@dataclass(frozen=True)
class Parameter:
    """One enumerated choice offered for a run."""

    name: str
    label: str
    choices: tuple[str, ...]
    default: str


@dataclass(frozen=True)
class RunEntry:
    """One runnable entry: an ordered list of steps and its parameters."""

    id: str
    name: str
    description: str
    steps: tuple[tuple[str, ...], ...]
    parameters: tuple[Parameter, ...] = ()

    def parameter(self, name: str) -> Parameter | None:
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter
        return None


def load_catalogue(path: Path | str = DEFAULT_CATALOGUE_PATH) -> tuple[RunEntry, ...]:
    """Read and validate the catalogue at ``path``.

    Every violation raises :class:`CatalogueError` with the offending entry named
    in the message. Validation is strict on purpose: the catalogue is edited by
    hand between experiments, and a typo that reaches a run costs GPU hours.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogueError(f"catalogue not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogueError(f"catalogue {path} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("runs"), list):
        raise CatalogueError(f"catalogue {path} must be an object with a 'runs' list")

    entries: list[RunEntry] = []
    seen: set[str] = set()
    for index, item in enumerate(raw["runs"]):
        entry = _parse_entry(item, index)
        if entry.id in seen:
            raise CatalogueError(f"duplicate run id {entry.id!r}")
        seen.add(entry.id)
        entries.append(entry)

    if not entries:
        raise CatalogueError(f"catalogue {path} declares no runs")
    return tuple(entries)


def _parse_entry(item: Any, index: int) -> RunEntry:
    where = f"run at position {index}"
    if not isinstance(item, dict):
        raise CatalogueError(f"{where} is not an object")

    entry_id = item.get("id")
    if not isinstance(entry_id, str) or not entry_id:
        raise CatalogueError(f"{where} has no id")
    if not _ID_PATTERN.match(entry_id):
        raise CatalogueError(f"run id {entry_id!r} must match [a-z0-9-]+")
    where = f"run {entry_id!r}"

    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise CatalogueError(f"{where} has an empty name")
    description = item.get("description")
    if not isinstance(description, str) or not description.strip():
        raise CatalogueError(f"{where} has an empty description")

    parameters = _parse_parameters(item.get("parameters", []), where)
    steps = _parse_steps(item.get("steps"), where)
    _check_placeholders(steps, parameters, where)

    return RunEntry(
        id=entry_id,
        name=name,
        description=description,
        steps=steps,
        parameters=parameters,
    )


def _parse_parameters(raw: Any, where: str) -> tuple[Parameter, ...]:
    if not isinstance(raw, list):
        raise CatalogueError(f"{where}: parameters must be a list")

    parameters: list[Parameter] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise CatalogueError(f"{where}: each parameter must be an object")
        name = item.get("name")
        if not isinstance(name, str) or not _PARAMETER_NAME_PATTERN.match(name):
            raise CatalogueError(f"{where}: parameter name {name!r} must match [a-z][a-z0-9_]*")
        if name in seen:
            raise CatalogueError(f"{where}: duplicate parameter {name!r}")
        seen.add(name)

        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise CatalogueError(f"{where}: parameter {name!r} has an empty label")

        choices = item.get("choices")
        if not isinstance(choices, list) or not choices:
            raise CatalogueError(f"{where}: parameter {name!r} has no choices")
        if not all(isinstance(choice, str) and choice for choice in choices):
            raise CatalogueError(f"{where}: parameter {name!r} has a non-string choice")
        if len(set(choices)) != len(choices):
            raise CatalogueError(f"{where}: parameter {name!r} has duplicate choices")

        default = item.get("default")
        if default not in choices:
            raise CatalogueError(
                f"{where}: parameter {name!r} default {default!r} is not one of its choices"
            )

        parameters.append(
            Parameter(name=name, label=label, choices=tuple(choices), default=default)
        )
    return tuple(parameters)


def _parse_steps(raw: Any, where: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw, list) or not raw:
        raise CatalogueError(f"{where}: steps must be a non-empty list")

    steps: list[tuple[str, ...]] = []
    for position, step in enumerate(raw):
        step_where = f"{where}: step {position + 1}"
        if not isinstance(step, list) or not step:
            raise CatalogueError(f"{step_where} must be a non-empty list of strings")
        if not all(isinstance(element, str) and element for element in step):
            raise CatalogueError(f"{step_where} has a non-string or empty element")
        # AD2. The first element being `-m` is what excludes an interpreter, a
        # git command, and anything else that is not a module in this repository.
        if step[0] != "-m":
            raise CatalogueError(
                f"{step_where} must begin with '-m' (got {step[0]!r}); the catalogue holds module "
                "invocations, not interpreters"
            )
        if len(step) < 2:
            raise CatalogueError(f"{step_where} names no module after '-m'")
        steps.append(tuple(step))
    return tuple(steps)


def _check_placeholders(
    steps: Sequence[Sequence[str]], parameters: Sequence[Parameter], where: str
) -> None:
    """Both directions. An undeclared placeholder is a crash at run time; a
    declared parameter nothing uses is a dropdown that does nothing."""
    declared = {parameter.name for parameter in parameters}
    used = set(_placeholders(steps))

    undeclared = sorted(used - declared)
    if undeclared:
        raise CatalogueError(f"{where}: steps use undeclared parameters: {', '.join(undeclared)}")
    unused = sorted(declared - used)
    if unused:
        raise CatalogueError(f"{where}: parameters appear in no step: {', '.join(unused)}")


def _placeholders(steps: Sequence[Sequence[str]]) -> Iterable[str]:
    for step in steps:
        for element in step:
            yield from _PLACEHOLDER_PATTERN.findall(element)


def resolve(entry: RunEntry, values: Mapping[str, str]) -> tuple[list[str], ...]:
    """Substitute ``values`` into ``entry``'s steps and return the argv lists.

    A missing parameter takes its declared default. A value outside a parameter's
    choices, or a key naming no parameter at all, raises rather than being
    ignored -- silently dropping an unknown key would let a stale page run
    something other than what it displayed.
    """
    unknown = sorted(set(values) - {parameter.name for parameter in entry.parameters})
    if unknown:
        raise CatalogueError(f"run {entry.id!r}: unknown parameters: {', '.join(unknown)}")

    resolved: dict[str, str] = {}
    for parameter in entry.parameters:
        value = values.get(parameter.name, parameter.default)
        if not isinstance(value, str) or value not in parameter.choices:
            raise CatalogueError(
                f"run {entry.id!r}: {value!r} is not an allowed value for {parameter.name!r} "
                f"(choices: {', '.join(parameter.choices)})"
            )
        resolved[parameter.name] = value

    return tuple([_substitute(element, resolved) for element in step] for step in entry.steps)


def _substitute(element: str, values: Mapping[str, str]) -> str:
    return _PLACEHOLDER_PATTERN.sub(lambda match: values[match.group(1)], element)


def command_line(argv: Sequence[str]) -> str:
    """The literal line a human would type, for display only. Never parsed back."""
    return "python -u " + " ".join(shlex.quote(element) for element in argv)
