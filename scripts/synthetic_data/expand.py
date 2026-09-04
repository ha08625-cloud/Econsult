"""Lexical variant expansion for finished synthetic datasets.

A few hundred fragments recombined thousands of times means each fragment's
*wording* is repeated thousands of times, and the lint measured what that costs:
``fever`` sits on 41 of the 45 ``fever_null_historical`` lines and 0 of the 50
``fever_null_attribution`` ones. A model can learn "the word `fever` means
displaced" from a skew like that as easily as from a token confined to one file.
This module rewrites finished examples with directional, whole-word, literal
substitutions so that the *choice of word* stops carrying information about the
label.

**It adds no ideas and no effective sample size.** One line written twelve ways
is one idea. The expanded tree holds exactly as many examples as the clean one,
carrying the same ``example_id``s and the same ``fragments`` provenance, so the
honest count still comes from there and no report may quote this pass as growth.

It is **post-processing over the JSONL**, in the shape
:mod:`~scripts.synthetic_data.noise` already has, and for the same reasons
(``arch_training.md`` 12.6, and this plan's DD1). Editing library text would
change each untagged line's cluster key -- ``manifest.cluster_key`` is
``cluster_id or normalise(text)`` -- and therefore its split, so a library-level
expander silently repartitions the data and the two arms stop being comparable.
Touching no library file means no cluster key moves, the generator stays
byte-identical, the golden digest holds, and every expanded example is paired by
``example_id`` with its clean original, which is what makes the decision metric
a paired statistic.

**The one risk worth naming**, the same one 12.6 names. Every other step fixes
the label *before* the text exists, so the text cannot make the label wrong
(section 2). This step edits text *after* the label is fixed. Three layers stand
against that, two of them mechanical and both at rule-validation time, so a bad
rule fails before a single byte is written (DD6):

* the rule's **declared invariant** -- human-written, human-reviewed, and the
  residual risk, because nothing mechanical catches a swap that changes the
  referent without touching a structural token;
* **structural-token invariance** -- the :data:`~.noise.STRUCTURAL_FROZEN`
  subsequence must be identical between ``find`` and ``replace``, compared after
  contraction normalisation so ``haven't -> have not`` is not falsely flagged;
* **signal-lexicon invariance** -- via :func:`~.lint.lexicon_matches`, a rule may
  not change whether its phrase reads as its own signal's language, and may not
  introduce another signal's language that ``find`` did not already carry.

Nothing in the selection path reads ``labels`` or ``meta``, and a test asserts
it. That is what makes DD5 a property of the architecture rather than a
discipline: because rules are scoped to a *signal* and applied to whole example
text with no sight of the label, a rule **cannot** be applied to ``true``
examples and not to ``null`` ones, so the pass cannot manufacture the very
shortcut it exists to remove. The skew is still measured -- the sidecar reports
realised substitutions per hundred words by label and by label mode -- and a
gap there is telemetry about the libraries, not a label-aware pass.

**The rule format is deliberately literal.** ``find`` and ``replace`` are fixed
strings; there is no pattern language, no capture group and no numeric range.
That is a deliberate limit rather than an unfinished one. Varying a measurement
-- a temperature of 38.4 swept across 37.6 to 41.0, say -- looks like the safest
possible rewrite and is not: the fever libraries already encode the ~38.0
threshold (36.5 and 36.8 in the normal-temperature lines, 38.2 and 39.5 in the
fever ones), so a sweep across it walks a ``fever_true`` line into saying the
patient's temperature was normal, and **neither mechanical layer above can see
it** -- the fever lexicon holds no numeric terms and ``STRUCTURAL_FROZEN`` holds
no digits. Numeric variation is therefore a *different rule kind*, needing a
per-label-class safe band and a fourth validation layer, and it arrives as an
explicit decision or not at all. See
``reports/encoder_training/2026-09-03-paraphrase-flip-diagnostic.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .lint import SIGNAL_LEXICONS, lexicon_matches
from .noise import (
    LABEL_MODES,
    LABELS,
    RECORD_KEYS,
    STRUCTURAL_FROZEN,
    TREE_AGREEMENT_FIELDS,
    NoiseError,
    check_directories,
    count_words,
    example_rng,
    fold_token,
    label_name,
    read_sidecar,
    sidecar_path,
    split_words,
)
from .recombine import _length_stats


class ExpandError(RuntimeError):
    """A rule file, dataset or configuration the pass refuses to expand.

    Raised rather than warned about, for the reason :class:`~.noise.NoiseError`
    is: every failure mode here is silent otherwise. A rule that shifts a label
    produces a tree that looks fine, trains fine, and is wrong in exactly the
    way section 2 exists to prevent.
    """


# ---------------------------------------------------------------------------
# The rule format
# ---------------------------------------------------------------------------

#: Tiers a rule may declare. Tier C (aspect and opener rewrites) is out of scope
#: for this pass and has no value here: it needs rules scoped to a *library*,
#: which post-processing cannot express, because example text carries no
#: character offsets back to its source fragments (DD1, DD4).
TIERS = ("A", "B")

#: Closed key set for a rule. An unknown key is an error rather than a comment,
#: for the reason ``recombine._NULL_ON_KEYS`` is closed: a typo in an optional
#: key is otherwise a silently ignored instruction, and here the ignored
#: instruction could be the one bounding a substitution's safety.
RULE_KEYS = frozenset({"id", "tier", "find", "replace", "weight", "invariant"})

#: Keys a rule may not omit. ``weight`` is the only optional one.
REQUIRED_RULE_KEYS = frozenset({"id", "tier", "find", "replace", "invariant"})

#: Closed key set for the file itself.
FILE_KEYS = frozenset({"signal", "rules"})

#: Default weight when a rule does not declare one.
DEFAULT_WEIGHT = 1.0

#: Share of examples the directory pass leaves completely unexpanded. Mirrors
#: :data:`~.noise.DEFAULT_CLEAN_SHARE` and exists for a related reason: a tree
#: where every matchable phrase has been rewritten is its own kind of
#: unrealistic, and leaving a share untouched keeps the original wording in the
#: training distribution rather than replacing it.
DEFAULT_CLEAN_SHARE = 0.25

#: Contractions expanded before the structural-token subsequence is taken, so
#: DD6 layer 2 compares like with like. ``haven't`` folds to one frozen token
#: and ``have not`` to two; without this a Tier A rule pairing them -- the whole
#: point of Tier A -- would fail the layer that exists to catch a rule *dropping*
#: a negation.
#:
#: Both the apostrophised and the bare spelling appear, because
#: :func:`~.noise.fold_token` does not strip internal apostrophes and the noise
#: pass can produce the bare form. Keyed on the folded spelling.
CONTRACTION_EXPANSIONS: Mapping[str, tuple[str, ...]] = {
    "aren't": ("are", "not"),
    "arent": ("are", "not"),
    "can't": ("can", "not"),
    "cant": ("can", "not"),
    "couldn't": ("could", "not"),
    "couldnt": ("could", "not"),
    "didn't": ("did", "not"),
    "didnt": ("did", "not"),
    "don't": ("do", "not"),
    "dont": ("do", "not"),
    "hasn't": ("has", "not"),
    "hasnt": ("has", "not"),
    "haven't": ("have", "not"),
    "havent": ("have", "not"),
    "he's": ("he", "is"),
    "hes": ("he", "is"),
    "i'm": ("i", "am"),
    "im": ("i", "am"),
    "i've": ("i", "have"),
    "ive": ("i", "have"),
    "isn't": ("is", "not"),
    "isnt": ("is", "not"),
    "she's": ("she", "is"),
    "shes": ("she", "is"),
    "wasn't": ("was", "not"),
    "wasnt": ("was", "not"),
    "won't": ("will", "not"),
    "wont": ("will", "not"),
    "wouldn't": ("would", "not"),
    "wouldnt": ("would", "not"),
}


@dataclass(frozen=True)
class Rule:
    """One literal, directional, whole-word substitution.

    Directional on purpose (DD2). Flattening the fever table needs
    ``fever -> temperature`` *and* ``temperature -> fever``, because
    ``null_historical`` over-uses the first exactly as ``fever_true`` over-uses
    the second; each direction is its own rule with its own declared invariant
    and its own safety review, and neither implies the other. A symmetric
    synonym bag would produce "I checked my fever and it was high" from a real
    ``fever_true`` line.
    """

    id: str
    tier: str
    find: str
    replace: str
    weight: float
    invariant: str
    pattern: re.Pattern[str]

    @property
    def length(self) -> int:
        return len(self.find)


@dataclass(frozen=True)
class RuleSet:
    """A signal's rules, and the provenance the sidecar records."""

    signal: str
    rules: tuple[Rule, ...]
    path: str
    digest: str

    def __iter__(self) -> Iterable[Rule]:
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)


# ---------------------------------------------------------------------------
# Rule validation -- DD6 layers 2 and 3, at load time
# ---------------------------------------------------------------------------


def structural_sequence(text: str) -> tuple[str, ...]:
    """The :data:`~.noise.STRUCTURAL_FROZEN` tokens of ``text``, in order.

    Contractions are expanded first (:data:`CONTRACTION_EXPANSIONS`) so that the
    comparison DD6 layer 2 makes is about *which structural words are present*
    rather than about how they happen to be spelt. Everything else is dropped:
    the sequence is what must survive a substitution, not the substitution.
    """
    tokens: list[str] = []
    for token in split_words(text):
        folded = fold_token(token.word)
        if not folded:
            continue
        for word in CONTRACTION_EXPANSIONS.get(folded, (folded,)):
            if word in STRUCTURAL_FROZEN:
                tokens.append(word)
    return tuple(tokens)


def _reject(rule_id: str, layer: str, why: str) -> ExpandError:
    """Build the one error message a rule author will actually read.

    Naming the rule, the layer and the reason is not decoration: a rule file is
    written by hand and these messages are the whole of that person's feedback
    loop.
    """
    return ExpandError(f"rule {rule_id!r} rejected by {layer}: {why}")


def check_matchable(rule_id: str, find: str, replace: str) -> None:
    """Layer 0: a rule that cannot be matched whole-word at all.

    Whole-word matching is not a nicety. Section 8 records why: "hot" matches
    inside ``lithotripsy``, ``photos`` and ``shot``. A ``find`` that begins or
    ends mid-word cannot be anchored, so it is refused rather than silently
    matched loosely.
    """
    for name, value in (("find", find), ("replace", replace)):
        if not value:
            raise _reject(rule_id, "whole-word matchability", f"{name!r} is empty")
        if value != value.strip():
            raise _reject(
                rule_id,
                "whole-word matchability",
                f"{name!r} has leading or trailing whitespace ({value!r}); "
                "matching is literal, so the space would have to be in the text too",
            )
    for name, value in (("find", find), ("replace", replace)):
        for edge, char in (("starts", value[0]), ("ends", value[-1])):
            if not (char.isalnum() or char == "_"):
                raise _reject(
                    rule_id,
                    "whole-word matchability",
                    f"{name!r} {edge} on {char!r}, which is not a word character; "
                    "a whole-word boundary cannot be anchored there",
                )


def check_structural_invariance(rule_id: str, find: str, replace: str) -> None:
    """DD6 layer 2: the structural-token subsequence must be identical.

    A rule that inserts "not", drops "my", or turns "had" into "have" fails
    here, before a single byte is written. Those four groups -- negation,
    person, tense and modality -- are what the labels actually hang on: negation
    decides ``true`` from ``false``, person and tense decide the null axes, and
    modality separates a hard-case ``null`` from a claim.
    """
    before = structural_sequence(find)
    after = structural_sequence(replace)
    if before != after:
        raise _reject(
            rule_id,
            "DD6 layer 2 (structural-token invariance)",
            f"the frozen-token sequence changes from {list(before)} to {list(after)}. "
            "Negation, person, tense and modality are what the label hangs on, so a "
            "substitution may not add, drop or reorder any of them",
        )


def check_lexicon_invariance(rule_id: str, find: str, replace: str, signal: str) -> None:
    """DD6 layer 3: signal-lexicon match status may not move.

    Two halves, and they fail for different reasons. Changing whether the phrase
    reads as *its own* signal's language turns a line the lint can see into one
    it cannot, or the reverse. Introducing *another* signal's language is the
    one thing the provisional plan's "re-run the lint over the expanded tree"
    was for -- a substitution putting, say, urinary language into a library
    declared silent on it -- caught here per-rule instead, which is cheaper and
    says which rule is at fault.
    """
    own_before = lexicon_matches(find, signal)
    own_after = lexicon_matches(replace, signal)
    if bool(own_before) != bool(own_after):
        raise _reject(
            rule_id,
            f"DD6 layer 3 (signal-lexicon invariance, {signal})",
            f"{find!r} {'matches' if own_before else 'does not match'} its own signal's "
            f"lexicon and {replace!r} {'does' if own_after else 'does not'}; a substitution "
            "may not change whether a phrase reads as the signal's own language",
        )
    for other in sorted(SIGNAL_LEXICONS):
        if other == signal:
            continue
        if lexicon_matches(replace, other) and not lexicon_matches(find, other):
            raise _reject(
                rule_id,
                f"DD6 layer 3 (signal-lexicon invariance, {other})",
                f"{replace!r} reads as {other} language and {find!r} does not; the "
                "substitution would put another signal's language into a library that may "
                "be declared silent on it",
            )


def compile_rule(payload: Mapping[str, object], *, signal: str) -> Rule:
    """Validate one rule object and return it, or explain which layer refused."""
    if not isinstance(payload, Mapping):
        raise ExpandError(f"every entry of 'rules' must be an object, got {type(payload).__name__}")

    raw_id = payload.get("id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        raise ExpandError(f"a rule has no usable 'id' (got {raw_id!r})")
    rule_id = raw_id

    unknown = sorted(set(payload) - RULE_KEYS)
    if unknown:
        raise _reject(
            rule_id,
            "the rule schema",
            f"unknown key(s) {unknown}; the key set is closed ({sorted(RULE_KEYS)}), because a "
            "typo in an optional key is otherwise a silently ignored instruction",
        )
    missing = sorted(REQUIRED_RULE_KEYS - set(payload))
    if missing:
        raise _reject(rule_id, "the rule schema", f"missing required key(s) {missing}")

    tier = payload["tier"]
    if tier not in TIERS:
        raise _reject(
            rule_id,
            "the rule schema",
            f"tier {tier!r} is not one of {list(TIERS)}. Tier C needs per-library scoping, "
            "which post-processing cannot express, and is a separate ticket",
        )

    for name in ("find", "replace", "invariant"):
        if not isinstance(payload[name], str):
            raise _reject(rule_id, "the rule schema", f"{name!r} must be a string")
    find = payload["find"]
    replace = payload["replace"]

    invariant = payload["invariant"].strip()
    if not invariant:
        raise _reject(
            rule_id,
            "the rule schema",
            "'invariant' is empty. It must state what the substitution preserves -- tense, "
            "person, certainty, polarity -- because it is the only layer that catches a swap "
            "changing the referent without touching a structural token, and a rule with no "
            "written justification is the one thing no check can recover",
        )

    weight = payload.get("weight", DEFAULT_WEIGHT)
    if isinstance(weight, bool) or not isinstance(weight, (int, float)):
        raise _reject(rule_id, "the rule schema", f"'weight' must be a number, got {weight!r}")
    if weight <= 0:
        raise _reject(rule_id, "the rule schema", f"'weight' must be positive, got {weight}")

    if find == replace:
        raise _reject(rule_id, "the rule schema", "'find' and 'replace' are identical")

    check_matchable(rule_id, find, replace)
    check_structural_invariance(rule_id, find, replace)
    check_lexicon_invariance(rule_id, find, replace, signal)

    return Rule(
        id=rule_id,
        tier=tier,
        find=find,
        replace=replace,
        weight=float(weight),
        invariant=invariant,
        # Lookarounds rather than ``\b`` so the anchor is explicit and holds for
        # a multi-word ``find``. Case-insensitive on the way in; the output's
        # case is decided by the source (:func:`apply_case`).
        pattern=re.compile(rf"(?<!\w){re.escape(find)}(?!\w)", re.IGNORECASE),
    )


def parse_rules(payload: object, *, source: str, digest: str) -> RuleSet:
    """Validate a whole rule file. Every layer runs before any file is written."""
    if not isinstance(payload, Mapping):
        raise ExpandError(f"{source} is not a JSON object")
    unknown = sorted(set(payload) - FILE_KEYS)
    if unknown:
        raise ExpandError(
            f"{source} has unknown top-level key(s) {unknown}; expected {sorted(FILE_KEYS)}"
        )
    missing = sorted(FILE_KEYS - set(payload))
    if missing:
        raise ExpandError(f"{source} is missing top-level key(s) {missing}")

    signal = payload["signal"]
    if not isinstance(signal, str) or signal not in SIGNAL_LEXICONS:
        raise ExpandError(
            f"{source} declares signal {signal!r}, which has no lexicon; "
            f"expected one of {sorted(SIGNAL_LEXICONS)}"
        )
    raw_rules = payload["rules"]
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ExpandError(f"{source} declares no rules")

    rules: list[Rule] = []
    seen: set[str] = set()
    for entry in raw_rules:
        rule = compile_rule(entry, signal=signal)
        if rule.id in seen:
            raise ExpandError(f"{source} declares rule id {rule.id!r} twice")
        seen.add(rule.id)
        rules.append(rule)
    return RuleSet(signal=signal, rules=tuple(rules), path=source, digest=digest)


def load_rules(path: Path) -> RuleSet:
    """Read and validate one signal's rule file."""
    if not path.is_file():
        raise ExpandError(f"no rule file at {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ExpandError(f"{path} is not valid JSON: {error}") from error
    digest = hashlib.sha256(raw).hexdigest()
    return parse_rules(payload, source=str(path), digest=digest)


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """One non-overlapping span of the text that at least one rule matches.

    ``candidates`` are the rules matching this *exact* span, sorted by id so the
    weighted draw is reproducible whatever order the rule file listed them in.
    """

    start: int
    end: int
    candidates: tuple[Rule, ...]


def find_sites(text: str, rules: Sequence[Rule]) -> tuple[list[Site], int]:
    """Collect left-to-right, non-overlapping match sites, longest match first.

    Longest-first at a position is what makes "a high temperature" beat
    "temperature" (DD3), so an author can write the specific rule and the
    general one and get the specific one where it applies. Returns the sites and
    the number of matches discarded for overlapping a site already taken --
    telemetry the sidecar reports rather than a silent loss.

    Reads ``text`` and nothing else. There is no label in scope here and that is
    the whole safety argument.
    """
    longest: dict[int, int] = {}
    at_span: dict[tuple[int, int], list[Rule]] = {}
    for rule in rules:
        for match in rule.pattern.finditer(text):
            start, end = match.start(), match.end()
            longest[start] = max(longest.get(start, 0), end)
            at_span.setdefault((start, end), []).append(rule)

    sites: list[Site] = []
    overlapping = 0
    cursor = 0
    for start in sorted(longest):
        end = longest[start]
        if start < cursor:
            overlapping += 1
            continue
        candidates = sorted(at_span[(start, end)], key=lambda rule: rule.id)
        sites.append(Site(start=start, end=end, candidates=tuple(candidates)))
        cursor = end
    return sites, overlapping


def apply_case(source: str, replacement: str) -> str:
    """Carry the source span's leading capitalisation onto the replacement.

    Matching is case-insensitive and the output is not: a rule written
    ``a fever -> a temperature`` must not lowercase a sentence opener. Only the
    first character is carried, because that is the only case difference a
    literal rule can be responsible for -- anything else is the author's
    spelling of ``replace``.
    """
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


@dataclass(frozen=True)
class ExpandResult:
    """One example's rewritten text and the telemetry the sidecar reports.

    ``sites`` is how many non-overlapping spans the rules matched, ``selected``
    how many the per-site coin picked, and ``applied`` how many were rewritten.
    ``selected`` and ``applied`` are equal today -- unlike the noise pass, a
    selected site has no way to be refused, because every safety question was
    settled when the rule file loaded -- and both are reported anyway so that a
    future rule kind which *can* be refused does not need a new sidecar shape.
    """

    text: str
    rules: Counter[str]
    words: int
    sites: int
    selected: int
    applied: int
    overlapping: int


def expand_example(
    text: str,
    rng,
    *,
    rate: float,
    rules: Sequence[Rule],
) -> ExpandResult:
    """Rewrite one example's text, with the telemetry.

    Per DD3: sites are collected left to right, each is applied independently
    with probability ``rate``, and where several rules match the same span one
    is drawn by weight. The draw sees the text and the rules; it does not see
    the label, and :func:`find_sites` has no label in scope to see.
    """
    sites, overlapping = find_sites(text, rules)
    fired: Counter[str] = Counter()
    selected = 0
    pieces: list[str] = []
    cursor = 0
    for site in sites:
        if rng.random() >= rate:
            continue
        selected += 1
        if len(site.candidates) == 1:
            chosen = site.candidates[0]
        else:
            chosen = rng.choices(
                site.candidates, weights=[rule.weight for rule in site.candidates], k=1
            )[0]
        pieces.append(text[cursor : site.start])
        pieces.append(apply_case(text[site.start : site.end], chosen.replace))
        cursor = site.end
        fired[chosen.id] += 1
    pieces.append(text[cursor:])
    rewritten = "".join(pieces)
    return ExpandResult(
        text=rewritten,
        rules=fired,
        words=count_words(rewritten),
        sites=len(sites),
        selected=selected,
        applied=sum(fired.values()),
        overlapping=overlapping,
    )


def expand_text(text: str, rules: Sequence[Rule], rng, rate: float) -> tuple[str, Counter[str]]:
    """:func:`expand_example` without the telemetry, in the shape of
    :func:`~.noise.damage_text`."""
    result = expand_example(text, rng, rate=rate, rules=rules)
    return result.text, result.rules


# ---------------------------------------------------------------------------
# The directory pass
# ---------------------------------------------------------------------------

#: Where a signal's rules live. Deliberately **not** under ``data/synthetic/``,
#: which a test guards as holding nothing but the libraries and the manifest
#: (DD11). Getting this wrong fails CI, which is the intended behaviour.
RULES_ROOT = Path("data/expansion")


def rules_path(signal: str, root: Path | None = None) -> Path:
    """The conventional rule-file path for ``signal``."""
    return (RULES_ROOT if root is None else root) / f"{signal}.rules.json"


@dataclass
class ExpandTally:
    """Running totals behind the sidecar's ``expansion.realised`` block.

    Kept per label and per label mode because that is the DD5 instrument. The
    pass *cannot* be label-aware -- rules are scoped to a signal and applied to
    whole text with no sight of the label -- so a gap here is telemetry about the
    libraries, meaning a class whose lines simply contain fewer matchable
    phrases. It is measured on every run anyway, because if substitution density
    ever tracked the label the model would learn "rewritten implies fever" and
    nothing else in the pipeline would show it.
    """

    words: Counter[str] = field(default_factory=Counter)
    subs: Counter[str] = field(default_factory=Counter)
    mode_words: Counter[str] = field(default_factory=Counter)
    mode_subs: Counter[str] = field(default_factory=Counter)
    examples: Counter[str] = field(default_factory=Counter)
    clean: Counter[str] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    total_words: int = 0
    sites: int = 0
    selected: int = 0
    applied: int = 0
    overlapping: int = 0

    def add(self, result: ExpandResult, *, label: str, label_mode: str, was_clean: bool) -> None:
        applied = sum(result.rules.values())
        self.words[label] += result.words
        self.subs[label] += applied
        self.mode_words[label_mode] += result.words
        self.mode_subs[label_mode] += applied
        self.examples[label] += 1
        self.clean[label] += int(was_clean)
        self.rules.update(result.rules)
        self.total_words += result.words
        self.sites += result.sites
        self.selected += result.selected
        self.applied += result.applied
        self.overlapping += result.overlapping

    def merge(self, other: ExpandTally) -> None:
        for name in ("words", "subs", "mode_words", "mode_subs", "examples", "clean", "rules"):
            getattr(self, name).update(getattr(other, name))
        self.total_words += other.total_words
        self.sites += other.sites
        self.selected += other.selected
        self.applied += other.applied
        self.overlapping += other.overlapping

    @property
    def subs_per_hundred_words(self) -> float:
        total = sum(self.subs.values())
        return 0.0 if not self.total_words else round(100 * total / self.total_words, 4)

    def by_label_rates(self) -> dict[str, float]:
        return {
            label: (
                0.0
                if not self.words[label]
                else round(100 * self.subs[label] / self.words[label], 4)
            )
            for label in LABELS
        }

    def by_label_mode_rates(self) -> dict[str, float]:
        return {
            mode: (
                0.0
                if not self.mode_words[mode]
                else round(100 * self.mode_subs[mode] / self.mode_words[mode], 4)
            )
            for mode in LABEL_MODES
        }

    @property
    def largest_by_label_gap(self) -> float:
        """Widest spread in substitution density across the labels that appear.

        The one number worth reading first after a run. Not a tolerance check --
        the pass has no threshold to fail, and DD5 says a gap is a fact about the
        libraries -- but a gap far from zero is worth explaining before the tree
        is trained on.
        """
        rates = [rate for label, rate in self.by_label_rates().items() if self.words[label]]
        return 0.0 if len(rates) < 2 else round(max(rates) - min(rates), 4)

    def clean_share(self) -> dict[str, float]:
        return {
            label: (
                0.0
                if not self.examples[label]
                else round(self.clean[label] / self.examples[label], 4)
            )
            for label in LABELS
        }

    @property
    def overall_clean_share(self) -> float:
        total = sum(self.examples.values())
        return 0.0 if not total else round(sum(self.clean.values()) / total, 4)


def check_tree(
    paths: Sequence[Path],
    sidecars: Sequence[Mapping[str, object]],
    *,
    rules_dir: Path | None = None,
) -> dict[str, RuleSet]:
    """Refuse an input tree that cannot be expanded honestly, and load its rules.

    Four checks, all of which fail silently otherwise, and all of them startup
    errors. A tree already carrying an ``expansion`` block would be expanded
    twice, compounding in a way no rate describes. A tree carrying a ``noise``
    block is DD9: both passes multiply surface forms, so running them in one
    experiment makes the result unattributable. A signal with no rule file is
    the dangerous one -- the pass would run, write an identical tree, and the
    experiment would compare a tree against itself. And a tree whose files
    disagree on the fold configuration was half-regenerated, which presents at
    training time as a score nobody can explain.

    Returns the loaded rule set per signal, so the rules are validated once, up
    front, before a single byte is written.
    """
    if not paths:
        raise ExpandError("no *.jsonl files found under --in-dir")

    loaded: dict[str, RuleSet] = {}
    for path, stats in zip(paths, sidecars, strict=True):
        if "expansion" in stats:
            raise ExpandError(
                f"{sidecar_path(path)} already carries an 'expansion' block; expanding an "
                "expanded tree compounds the substitutions in a way no rate describes"
            )
        if "noise" in stats:
            raise ExpandError(
                f"{sidecar_path(path)} carries a 'noise' block. Expansion and the noise pass "
                "both multiply surface forms, so running them in one experiment makes the "
                "result unattributable (DD9). Expand the clean tree instead"
            )
        signal = stats.get("signal")
        if not isinstance(signal, str) or not signal:
            raise ExpandError(f"{sidecar_path(path)} records no 'signal'")
        if signal not in loaded:
            loaded[signal] = load_rules(rules_path(signal, rules_dir))

    for field_name in TREE_AGREEMENT_FIELDS:
        values = {json.dumps(stats.get(field_name), sort_keys=True) for stats in sidecars}
        if len(values) > 1:
            raise ExpandError(
                f"the sidecars under --in-dir disagree on {field_name!r} "
                f"({', '.join(sorted(values))}); this tree was half-regenerated, and expanding "
                "it would hide that until training time"
            )
    return loaded


def build_expansion_stats(
    stats: Mapping[str, object],
    *,
    tally: ExpandTally,
    texts: Sequence[tuple[str, str, str, str]],
    source_dir: str,
    seed: int,
    rate: float,
    clean_share: float,
    rule_set: RuleSet,
) -> dict:
    """Return the output sidecar: the input's, with two things changed.

    ``token_counts`` is recomputed from the rewritten texts, because a
    substitution changes a word count and a sidecar has to describe the file
    sitting next to it. Everything else is passed through untouched --
    ``fragments``, ``fragment_pool_sizes``, ``requested``, ``realised`` and the
    whole fold configuration all describe the *fragments*, and the fragments
    were not edited. ``generator_version`` in particular is not bumped: the
    three splits of a fold must agree on it (``dataset._check_fold_agreement``)
    and an expanded tree is still that generator's output.

    An ``expansion`` block is added. Its presence is the marker that a tree has
    been expanded -- a clean tree has no such key -- which is also the guard
    against double-expanding. ``dataset._read_stats`` only checks for required
    keys, so an extra top-level block is additive and safe.
    """
    output = deepcopy(dict(stats))

    by_label: dict[str, list[str]] = {label: [] for label in LABELS}
    by_mode: dict[str, list[str]] = {mode: [] for mode in LABEL_MODES}
    by_count: dict[str, list[str]] = {}
    for text, label, mode, count_key in texts:
        by_label.setdefault(label, []).append(text)
        by_mode.setdefault(mode, []).append(text)
        by_count.setdefault(count_key, []).append(text)
    previous = output.get("token_counts")
    previous_counts = previous.get("by_fragment_count", {}) if isinstance(previous, dict) else {}
    count_keys = sorted(set(by_count) | set(previous_counts), key=lambda key: (len(key), key))
    output["token_counts"] = {
        "by_label": {label: _length_stats(by_label.get(label, [])) for label in LABELS},
        "by_label_mode": {mode: _length_stats(by_mode.get(mode, [])) for mode in LABEL_MODES},
        "by_fragment_count": {key: _length_stats(by_count.get(key, [])) for key in count_keys},
    }

    output["expansion"] = {
        "source_dir": source_dir,
        "seed": seed,
        "requested": {
            "rate": rate,
            "clean_share": clean_share,
            "rules": {
                "path": rule_set.path,
                "digest": rule_set.digest,
                "signal": rule_set.signal,
                "count": len(rule_set),
                "by_tier": dict(sorted(Counter(rule.tier for rule in rule_set).items())),
            },
        },
        "realised": {
            # DD5. The pass cannot read the label, so these rows describe the
            # libraries rather than the pass. A gap far from zero means one
            # class's lines simply carry fewer matchable phrases, and the report
            # must say so rather than reading it as a label-aware pass.
            "substitutions_per_hundred_words": {
                "by_label": tally.by_label_rates(),
                "by_label_mode": tally.by_label_mode_rates(),
                "overall": tally.subs_per_hundred_words,
                "largest_by_label_gap": tally.largest_by_label_gap,
            },
            "clean_share": {
                "by_label": tally.clean_share(),
                "overall": tally.overall_clean_share,
            },
            "rules": dict(sorted(tally.rules.items())),
            # ``sites`` minus ``selected`` is the rate at work; ``selected``
            # minus ``applied`` is zero today and reported so that a rule kind
            # which can be refused does not need a new sidecar shape.
            # ``rejected_overlapping`` is matches discarded for landing inside a
            # span already taken -- a longest-match consequence, not a loss.
            "sites": {
                "total": tally.sites,
                "selected": tally.selected,
                "applied": tally.applied,
                "rejected_overlapping": tally.overlapping,
            },
        },
    }
    return output


def expand_file(
    in_path: Path,
    out_path: Path,
    *,
    rate: float,
    seed: int,
    clean_share: float,
    rule_set: RuleSet,
    stats: Mapping[str, object] | None = None,
) -> ExpandTally:
    """Rewrite one split's JSONL and write it, with its sidecar, to ``out_path``.

    ``example_id``, ``split``, ``labels`` and ``meta`` are copied through
    untouched: only ``text`` is edited, and the record's key order is
    :data:`~.noise.RECORD_KEYS` so a diff against the clean tree shows exactly
    that. Each example draws its own RNG from its id rather than its position,
    then draws the clean-share coin before the text is looked at.
    """
    stats = _read_sidecar(in_path) if stats is None else stats

    tally = ExpandTally()
    rows: list[tuple[str, str, str, str]] = []
    records: list[dict] = []
    with in_path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ExpandError(f"{in_path} line {number} is not valid JSON: {error}") from error

    for record in records:
        rng = example_rng(seed, record["example_id"])
        # First draw of the example, before the text is even looked at, so the
        # clean share cannot depend on anything about the example.
        was_clean = rng.random() < clean_share
        if was_clean:
            result = ExpandResult(
                text=record["text"],
                rules=Counter(),
                words=count_words(record["text"]),
                sites=0,
                selected=0,
                applied=0,
                overlapping=0,
            )
        else:
            result = expand_example(record["text"], rng, rate=rate, rules=rule_set.rules)
        record["text"] = result.text
        meta = record.get("meta", {})
        label = label_name(record.get("labels", {}).get(rule_set.signal))
        label_mode = meta.get("label_mode", "unknown")
        tally.add(result, label=label, label_mode=label_mode, was_clean=was_clean)
        rows.append((result.text, label, label_mode, str(len(meta.get("fragment_ids", [])))))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            ordered = {key: record[key] for key in RECORD_KEYS if key in record}
            ordered.update({key: value for key, value in record.items() if key not in ordered})
            handle.write(json.dumps(ordered, ensure_ascii=False) + "\n")

    output_stats = build_expansion_stats(
        stats,
        tally=tally,
        texts=rows,
        source_dir=str(in_path.parent),
        seed=seed,
        rate=rate,
        clean_share=clean_share,
        rule_set=rule_set,
    )
    with sidecar_path(out_path).open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(output_stats, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    return tally


def _read_sidecar(path: Path) -> dict:
    """:func:`~.noise.read_sidecar`, with the error re-raised as this pass's."""
    try:
        return read_sidecar(path)
    except NoiseError as error:
        raise ExpandError(str(error)) from None


def _check_directories(in_dir: Path, out_dir: Path, *, force: bool, root: Path | None) -> None:
    """:func:`~.noise.check_directories`, reused rather than mirrored.

    The path arithmetic -- both trees under ``data/synthetic/generated/``,
    neither equal to nor nested in the other, a non-empty target refused without
    ``--force`` -- is identical for the two passes and is exactly the kind of
    guard that goes wrong when it is copied and one copy is fixed. One of its
    messages says "noises" where this pass would say "expands"; that is a
    smaller cost than a second implementation of the nesting check drifting away
    from this one.
    """
    try:
        check_directories(in_dir, out_dir, force=force, root=root)
    except NoiseError as error:
        raise ExpandError(str(error)) from None


def expand_tree(
    in_dir: Path,
    out_dir: Path,
    *,
    rate: float,
    seed: int = 42,
    clean_share: float = DEFAULT_CLEAN_SHARE,
    rules_dir: Path | None = None,
    force: bool = False,
    root: Path | None = None,
) -> ExpandTally:
    """Rewrite a whole fold tree, filenames and all, into ``out_dir``.

    Whole tree in, whole tree out. ``dataset.FOLD_FILENAME`` is how
    ``scripts/encoder_training/`` finds a fold at all, so an expanded file named
    anything else would simply be invisible to it; every file keeps its name,
    and anything that is neither a dataset nor a sidecar is copied through
    byte-for-byte so the output tree is a drop-in ``--data-dir`` or
    ``--test-dir``.
    """
    _check_directories(in_dir, out_dir, force=force, root=root)
    paths = sorted(in_dir.rglob("*.jsonl"))
    sidecars = [_read_sidecar(path) for path in paths]
    rule_sets = check_tree(paths, sidecars, rules_dir=rules_dir)

    known = {path for path in paths} | {sidecar_path(path) for path in paths}
    total = ExpandTally()
    for path, stats in zip(paths, sidecars, strict=True):
        target = out_dir / path.relative_to(in_dir)
        total.merge(
            expand_file(
                path,
                target,
                rate=rate,
                seed=seed,
                clean_share=clean_share,
                rule_set=rule_sets[stats["signal"]],
                stats=stats,
            )
        )

    for path in sorted(in_dir.rglob("*")):
        if not path.is_file() or path in known:
            continue
        target = out_dir / path.relative_to(in_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return total


def _rate(raw: str) -> float:
    value = float(raw)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(f"must be in (0, 1]: {raw}")
    return value


def _share(raw: str) -> float:
    value = float(raw)
    if not 0 <= value < 1:
        raise argparse.ArgumentTypeError(f"must be in [0, 1): {raw}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.synthetic_data.expand",
        description="Write a lexically expanded copy of a generated fold tree, ids and "
        "filenames intact.",
    )
    parser.add_argument("--in-dir", type=Path, required=True, help="a generated fold tree")
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="where the expanded copy goes; must be a sibling of --in-dir, never inside it",
    )
    parser.add_argument(
        "--rate",
        type=_rate,
        required=True,
        help="probability that any one match site is rewritten, drawn per site rather than per "
        "example (DD3). Required rather than defaulted: there is no rate that is obviously "
        "right, and a rate of 1 rewrites every occurrence, which is its own skew",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--clean-share",
        type=_share,
        default=DEFAULT_CLEAN_SHARE,
        help="share of examples left completely unexpanded, so the libraries' original wording "
        "stays in the training distribution rather than being replaced by it",
    )
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=None,
        help=f"where <signal>.rules.json lives (default {RULES_ROOT}). Deliberately outside "
        "data/synthetic/, which holds nothing but the libraries and the manifest",
    )
    parser.add_argument("--force", action="store_true", help="write into a non-empty --out-dir")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        tally = expand_tree(
            args.in_dir,
            args.out_dir,
            rate=args.rate,
            seed=args.seed,
            clean_share=args.clean_share,
            rules_dir=args.rules_dir,
            force=args.force,
        )
    except ExpandError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # The three numbers worth seeing without opening a sidecar: how much
    # rewriting actually happened, whether it happened equally across the
    # labels, and how many matches longest-match precedence swallowed.
    print(
        f"wrote {sum(tally.examples.values())} examples to {args.out_dir} "
        f"(substitutions/100 words={tally.subs_per_hundred_words}, "
        f"largest by-label gap={tally.largest_by_label_gap}, "
        f"sites={tally.sites}, applied={tally.applied}, "
        f"overlapping matches discarded={tally.overlapping})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
