"""Lexical variant expansion for finished synthetic datasets.

The fragment libraries say one thing one way. `fever` sits on 91% of
``fever_null_historical`` lines and 18% of ``fever_true`` ones, and
`temperature` sits on a quarter of the decisive lines and on no historical line
at all (``reports/synthetic_data/2026-09-03-token-label-association.md``). A
model can learn "temperature implies decisive, fever implies displaced" from
that as easily as from a token that appears in exactly one file, and nothing in
the lint can see it. This module rewrites finished examples with directional,
scoped, literal substitutions so that the *choice of word* stops carrying the
label.

**It adds no ideas and no effective sample size.** One line written twelve ways
is one idea. The expanded tree holds exactly as many examples as the clean one,
paired ``example_id`` for ``example_id``, which is what makes the decision
metric a paired statistic rather than a bespoke corpus.

This is **post-processing over the JSONL**, in the shape
:mod:`~scripts.synthetic_data.noise` already has, and for the same reasons plus
one of its own: ``manifest.cluster_key`` is ``cluster_id or normalise(text)``,
so editing a library's text moves an untagged line's cluster key and therefore
its split. A library-level expander would silently repartition the data and the
two arms of the experiment would stop being comparable. Touching no library
file means no cluster key moves, no split moves, the generator stays
byte-identical and the golden digest holds
(``arch_training.md`` 12.10, DD1).

**The label-safety question is the whole of the risk**, exactly as it is for the
noise pass: this is the second step that edits text after the label is fixed
(section 2). Three layers stand between a rule and a mislabelled line, and only
two of them are mechanical:

1. a **declared invariant** on every rule -- human-written, human-reviewed, and
   the residual risk;
2. **structural-token invariance** -- the sequence of
   :data:`~scripts.synthetic_data.noise.STRUCTURAL_FROZEN` tokens must survive
   the swap, compared after contraction normalisation so ``haven't`` ->
   ``have not`` is not falsely flagged;
3. **signal-lexicon invariance** -- the swap may not change whether the phrase
   reads as its own signal, and may not introduce another signal's language
   that the source phrase did not have.

All three run when the rule file *loads*, before a byte is written, so a bad
rule is rejected with its id and the layer that refused it rather than found in
a trained model.

Nothing in the substitution path reads ``labels`` or ``meta``. A rule therefore
*cannot* be applied to ``true`` examples and not to ``null`` ones, which closes
by construction the trap of a partial pass manufacturing exactly the shortcut
the pass exists to remove (DD5). The realised substitution density is measured
per label and per label mode anyway, and a skew there is telemetry about the
libraries rather than a label-aware pass.

**The rule format is deliberately literal.** ``find`` and ``replace`` are plain
phrases, not patterns, and the format **cannot express a numeric range at all**.
That is a decision rather than an omission. Varying a temperature value looks
like the safest possible rewrite and is the least safe one available: the fever
libraries encode the ~38.0 threshold in their numbers (36.5 and 36.8 in the
normal lines, 38.2 and 39.5 in the fever ones), no signal lexicon holds a
numeric term and :data:`STRUCTURAL_FROZEN` holds no digits, so a rule sweeping
``38.4`` to ``37.6`` passes both mechanical layers while walking a ``true`` line
into saying the patient's temperature was normal. Numeric variation is a
different rule kind needing a per-label-class safe band and a fourth validation
layer; it arrives as an explicit decision or not at all.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from .lint import SIGNAL_LEXICONS, lexicon_matches
from .noise import (
    GENERATED_ROOT,
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


class ExpansionError(RuntimeError):
    """A rule, a tree or a configuration the pass refuses to run.

    Raised rather than warned about, for the same reason
    :class:`~scripts.synthetic_data.noise.NoiseError` is: every failure mode
    here is silent otherwise. A rule that quietly changes a label produces a
    tree that looks fine, trains fine, and is wrong in a way only a human
    reading the rewritten lines would ever notice.
    """


#: Where rule files live, one per signal, named ``<signal>.rules.json``.
#:
#: Deliberately **not** under ``data/synthetic/``, which a test guards as
#: holding nothing but the fragment libraries and the manifest. A rule file is
#: not library text and putting it there would fail CI (DD11).
RULES_ROOT = Path("data/expansion")

#: Every key a rule may carry, and every one it must. Closed, so an unknown key
#: is an error rather than a comment: a misspelt ``weight`` that silently
#: defaulted, or an ``invariant`` typed as ``invariants``, would remove the one
#: layer of the safety argument no check can recover.
RULE_REQUIRED_KEYS = frozenset({"id", "tier", "find", "replace", "invariant"})
RULE_OPTIONAL_KEYS = frozenset({"weight"})
RULE_KEYS = RULE_REQUIRED_KEYS | RULE_OPTIONAL_KEYS

#: Top-level keys of a rule file. Closed for the same reason.
FILE_KEYS = frozenset({"signal", "rules"})

#: The two tiers this pass will run (DD4). Tier A is orthography and
#: contraction -- it cannot change which word a token is. Tier B is signal
#: vocabulary -- a real risk, and the one the three layers exist to bound.
#: Tier C (aspect and opener rewrites) needs a rule scoped to a *library*,
#: which post-processing cannot express, and is out of scope.
TIERS = ("A", "B")

#: Share of examples the pass leaves untouched.
#:
#: Same default as the noise pass, and for a related reason: the point is to
#: shift the vocabulary distribution, not to replace it. A tree in which every
#: ``fever`` became a ``temperature`` would have swapped one perfect
#: association for another.
DEFAULT_CLEAN_SHARE = 0.25

#: Structural tokens, folded once, for :func:`structural_sequence`.
_STRUCTURAL = frozenset(fold_token(word) for word in STRUCTURAL_FROZEN)

#: Contractions expanded before the layer-2 comparison, so that the Tier A
#: rules the pass exists to carry -- ``haven't`` -> ``have not``, ``I've`` ->
#: ``I have`` -- are not rejected by the check that protects them. Both the
#: apostrophised and the bare spelling are listed because
#: :data:`STRUCTURAL_FROZEN` lists both and the noise pass can produce either.
_CONTRACTIONS = {
    "dont": "do not",
    "don't": "do not",
    "didnt": "did not",
    "didn't": "did not",
    "havent": "have not",
    "haven't": "have not",
    "hasnt": "has not",
    "hasn't": "has not",
    "isnt": "is not",
    "isn't": "is not",
    "wasnt": "was not",
    "wasn't": "was not",
    "arent": "are not",
    "aren't": "are not",
    "cant": "can not",
    "can't": "can not",
    "couldnt": "could not",
    "couldn't": "could not",
    "wouldnt": "would not",
    "wouldn't": "would not",
    "wont": "will not",
    "won't": "will not",
    "im": "i am",
    "i'm": "i am",
    "ive": "i have",
    "i've": "i have",
    "hes": "he is",
    "he's": "he is",
    "shes": "she is",
    "she's": "she is",
}

_WORD_CHARACTER = re.compile(r"\w")

#: Curly apostrophes folded to straight before matching, so a rule written with
#: a straight apostrophe fires on a library line typed with a curly one. Both
#: are single characters, so the fold preserves every offset into the text --
#: which is what lets the pass slice the *original* string by indices found in
#: the folded one.
_APOSTROPHE_FOLD = {ord("‘"): "'", ord("’"): "'"}


# ---------------------------------------------------------------------------
# The rule format
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """One literal, directional, whole-word substitution.

    Directional, and that is the correction worth stating: flattening the
    fever table needs ``fever -> temperature`` *and* ``temperature -> fever``,
    because ``null_historical`` over-uses the first exactly as ``fever_true``
    over-uses the second. Each direction is its own rule with its own declared
    invariant and its own review; neither implies the other, and a symmetric
    synonym bag turns "I checked my temperature and it was high" into "I
    checked my fever and it was high" (DD2).
    """

    id: str
    tier: str
    find: str
    replace: str
    invariant: str
    weight: float = 1.0

    @property
    def needle(self) -> str:
        """The folded form matched against the folded text."""
        return fold_haystack(self.find)


@dataclass(frozen=True)
class RuleSet:
    """Every rule for one signal, with the provenance the sidecar records."""

    signal: str
    path: Path
    digest: str
    rules: tuple[Rule, ...]


def fold_haystack(text: str) -> str:
    """Lowercase ``text`` and fold curly apostrophes, preserving every offset.

    :func:`str.lower` is length-preserving for every character the libraries
    contain but not for every character in Unicode, so it is applied per
    character and skipped where it would not be -- an offset that shifted would
    slice the original string in the wrong place, silently.
    """
    folded = text.translate(_APOSTROPHE_FOLD)
    return "".join(
        lowered if len(lowered := character.lower()) == 1 else character for character in folded
    )


def structural_sequence(phrase: str) -> tuple[str, ...]:
    """The :data:`STRUCTURAL_FROZEN` tokens of ``phrase``, in order.

    Contractions are expanded first, so ``haven't`` and ``have not`` produce
    the same sequence. This is DD6 layer 2's whole comparison: negation decides
    ``true`` from ``false``, person and tense decide the null axes, and
    modality separates a hard-case ``null`` from an assertion, so a swap that
    inserts "not", drops "my" or turns "had" into "have" has changed the label
    whatever its author intended.
    """
    words: list[str] = []
    for token in split_words(phrase):
        folded = fold_token(token.word)
        if not folded:
            continue
        words.extend(_CONTRACTIONS.get(folded, folded).split())
    return tuple(word for word in words if word in _STRUCTURAL)


def _check_shape(raw: Mapping[str, object], index: int) -> Rule:
    """Turn one JSON object into a :class:`Rule`, or say why it is not one."""
    where = f"rule {index}"
    keys = set(raw)
    unknown = keys - RULE_KEYS
    if unknown:
        raise ExpansionError(
            f"{where}: unknown key(s) {', '.join(sorted(unknown))}; a rule carries only "
            f"{', '.join(sorted(RULE_KEYS))} and the key set is closed, so a misspelt key is a "
            "silently ignored rule rather than a comment"
        )
    missing = RULE_REQUIRED_KEYS - keys
    if missing:
        raise ExpansionError(f"{where}: missing required key(s) {', '.join(sorted(missing))}")

    for name in ("id", "tier", "find", "replace", "invariant"):
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise ExpansionError(f"{where}: {name!r} must be a non-empty string, got {value!r}")

    rule_id = str(raw["id"]).strip()
    tier = str(raw["tier"]).strip()
    if tier not in TIERS:
        raise ExpansionError(
            f"rule {rule_id!r}: tier {tier!r} is not one of {', '.join(TIERS)}. Tier C (aspect "
            "and opener rewrites) needs a rule scoped to a library, which post-processing "
            "cannot express, and is out of scope for this pass"
        )
    weight = raw.get("weight", 1.0)
    if not isinstance(weight, int | float) or isinstance(weight, bool) or weight <= 0:
        raise ExpansionError(f"rule {rule_id!r}: weight must be a positive number, got {weight!r}")
    return Rule(
        id=rule_id,
        tier=tier,
        find=str(raw["find"]),
        replace=str(raw["replace"]),
        invariant=str(raw["invariant"]).strip(),
        weight=float(weight),
    )


def _check_matchable(rule: Rule) -> None:
    """Layer 1 of the load check: the rule can be matched whole-word at all.

    ``find`` has to begin and end on a word character or the boundary test
    around a match site means nothing -- and matching *is* whole-word only,
    because section 8 already records why: "hot" appears inside ``lithotripsy``,
    ``photos`` and ``shot``.
    """
    for name, value in (("find", rule.find), ("replace", rule.replace)):
        if value != value.strip():
            raise ExpansionError(
                f"rule {rule.id!r}: {name} {value!r} has leading or trailing whitespace"
            )
    if not _WORD_CHARACTER.match(rule.find[0]) or not _WORD_CHARACTER.match(rule.find[-1]):
        raise ExpansionError(
            f"rule {rule.id!r}: find {rule.find!r} must start and end on a word character, or "
            "the whole-word boundary around a match site means nothing"
        )
    if fold_haystack(rule.find) == fold_haystack(rule.replace):
        raise ExpansionError(
            f"rule {rule.id!r}: find and replace differ only in case ({rule.find!r} -> "
            f"{rule.replace!r}); casing is the noise pass's business, not this one's"
        )


def _check_structural(rule: Rule) -> None:
    """Layer 2 of the load check: DD6's structural-token invariance."""
    before = structural_sequence(rule.find)
    after = structural_sequence(rule.replace)
    if before != after:
        raise ExpansionError(
            f"rule {rule.id!r}: structural-token invariance (DD6 layer 2). {rule.find!r} carries "
            f"{before or '()'} and {rule.replace!r} carries {after or '()'}. Those tokens are "
            "negation, person, tense and modality -- the swap changes the label, whatever it "
            "was meant to change"
        )


def _check_lexicons(rule: Rule, signal: str) -> None:
    """Layer 3 of the load check: DD6's signal-lexicon invariance.

    Two halves. The rule may not change whether its phrase reads as **its own**
    signal -- ``fever -> temperature`` is a swap inside the lexicon, ``fever ->
    headache`` walks a decisive line into saying nothing about fever. And it may
    not introduce **another** signal's language that ``find`` did not have,
    which is the one thing re-running the whole lint over the expanded tree was
    ever for, done per-rule: cheaper, and precise about which rule is at fault.
    """
    own_before = bool(lexicon_matches(rule.find, signal))
    own_after = bool(lexicon_matches(rule.replace, signal))
    if own_before != own_after:
        state = "no longer reads" if own_before else "reads"
        raise ExpansionError(
            f"rule {rule.id!r}: signal-lexicon invariance (DD6 layer 3). {rule.replace!r} "
            f"{state} as {signal} language, where {rule.find!r} does the opposite; the swap "
            "moves the line's own signal in or out of view"
        )
    for other in sorted(SIGNAL_LEXICONS):
        if other == signal:
            continue
        introduced = set(lexicon_matches(rule.replace, other)) - set(
            lexicon_matches(rule.find, other)
        )
        if introduced:
            raise ExpansionError(
                f"rule {rule.id!r}: signal-lexicon invariance (DD6 layer 3). {rule.replace!r} "
                f"introduces {other} language ({', '.join(sorted(introduced))}) that "
                f"{rule.find!r} does not carry; every library that must stay silent on "
                f"{other} would start talking about it"
            )


def parse_rules(payload: object, *, source: str) -> tuple[str, tuple[Rule, ...]]:
    """Validate a loaded rule document and return ``(signal, rules)``.

    File-free, so the tests can put a malformed document in front of every
    layer without touching a disk.
    """
    if not isinstance(payload, dict):
        raise ExpansionError(f"{source} is not a JSON object")
    unknown = set(payload) - FILE_KEYS
    if unknown:
        raise ExpansionError(f"{source}: unknown top-level key(s) {', '.join(sorted(unknown))}")
    signal = payload.get("signal")
    if not isinstance(signal, str) or signal not in SIGNAL_LEXICONS:
        raise ExpansionError(
            f"{source}: 'signal' must be one of {', '.join(sorted(SIGNAL_LEXICONS))}, "
            f"got {signal!r}"
        )
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ExpansionError(f"{source}: 'rules' must be a non-empty list")

    rules: list[Rule] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rules):
        if not isinstance(raw, dict):
            raise ExpansionError(f"{source}: rule {index} is not a JSON object")
        try:
            rule = _check_shape(raw, index)
            if rule.id in seen:
                raise ExpansionError(f"rule {rule.id!r}: duplicate id")
            seen.add(rule.id)
            _check_matchable(rule)
            _check_structural(rule)
            _check_lexicons(rule, signal)
        except ExpansionError as error:
            raise ExpansionError(f"{source}: {error}") from None
        rules.append(rule)
    return signal, tuple(rules)


def load_rules(path: Path) -> RuleSet:
    """Load and validate one signal's rule file.

    Every layer runs here, before the pass has opened a single dataset. A rule
    file is authored by a human and a rejection message is the whole of that
    person's feedback loop, so each one names the rule, the layer that refused
    it and why.
    """
    if not path.is_file():
        raise ExpansionError(f"no rule file at {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpansionError(f"{path} is not valid JSON: {error}") from error
    signal, rules = parse_rules(payload, source=str(path))
    return RuleSet(
        signal=signal,
        path=path,
        digest=hashlib.sha256(raw).hexdigest(),
        rules=rules,
    )


def rules_path(signal: str, rules_dir: Path | None = None) -> Path:
    """Where ``signal``'s rule file lives."""
    root = RULES_ROOT if rules_dir is None else rules_dir
    return root / f"{signal}.rules.json"


# ---------------------------------------------------------------------------
# The pass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchSite:
    """One non-overlapping place in a text where at least one rule fires.

    ``rules`` holds every rule whose ``find`` is the *longest* one matching at
    this position, so "a high temperature" beats "temperature" and the shorter
    rule is not merely outvoted but never considered at that site.
    """

    start: int
    end: int
    rules: tuple[Rule, ...]


def _is_word_character(character: str) -> bool:
    return bool(_WORD_CHARACTER.match(character))


def match_sites(text: str, rules: Sequence[Rule]) -> list[MatchSite]:
    """Walk ``text`` left to right collecting non-overlapping whole-word sites.

    Reads only the text and the rules. Nothing here can see a label, which is
    the mechanical half of the DD5 argument: a rule cannot fire on ``true``
    examples and not on ``null`` ones because nothing in this path knows which
    it is looking at.
    """
    haystack = fold_haystack(text)
    needles = [(rule, rule.needle) for rule in rules]
    sites: list[MatchSite] = []
    index = 0
    length = len(haystack)
    while index < length:
        if not _is_word_character(haystack[index]) or (
            index and _is_word_character(haystack[index - 1])
        ):
            index += 1
            continue
        best = 0
        candidates: list[Rule] = []
        for rule, needle in needles:
            end = index + len(needle)
            if end > length or haystack[index:end] != needle:
                continue
            if end < length and _is_word_character(haystack[end]):
                continue
            if len(needle) > best:
                best, candidates = len(needle), [rule]
            elif len(needle) == best:
                candidates.append(rule)
        if not candidates:
            index += 1
            continue
        sites.append(MatchSite(start=index, end=index + best, rules=tuple(candidates)))
        index += best
    return sites


def _match_leading_case(source: str, replacement: str) -> str:
    """Give ``replacement`` the leading capitalisation ``source`` had.

    Matching is case-insensitive so a rule written once fires at the start of a
    sentence too; the output is not, because "Temperature was 38.2" reading
    "temperature was 38.2" is a casing error the noise pass is supposed to
    introduce deliberately rather than one this pass leaks.
    """
    lead = next((character for character in source if character.isalpha()), "")
    if not lead.isupper():
        return replacement
    for index, character in enumerate(replacement):
        if character.isalpha():
            return replacement[:index] + character.upper() + replacement[index + 1 :]
    return replacement


@dataclass(frozen=True)
class ExpansionResult:
    """One example's rewritten text and the telemetry the sidecar reports.

    ``sites`` is how many places a rule could have fired, ``applied`` how many
    it did, and ``skipped`` why the rest did not -- today only the per-site rate
    coin, kept as a counter because a second reason is exactly the kind of thing
    that otherwise arrives unmeasured.
    """

    text: str
    applications: Counter[str]
    words: int
    sites: int
    applied: int
    skipped: Counter[str]


def expand_example(
    text: str,
    rules: Sequence[Rule],
    rng: random.Random,
    *,
    rate: float,
) -> ExpansionResult:
    """Rewrite one example, returning the text and its telemetry.

    A rule fires **per match site, not per example** (DD3): every site gets its
    own Bernoulli draw at ``rate``, so a line saying "fever" three times can
    have one, two, three or none of them moved, and the pass does not turn a
    long line into a wholesale rewrite. Where more than one rule matches a site
    the choice among them is by weight.
    """
    sites = match_sites(text, rules)
    applications: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    pieces: list[str] = []
    cursor = 0
    for site in sites:
        if rng.random() >= rate:
            skipped["rate_coin"] += 1
            continue
        chosen = rng.choices(site.rules, weights=[rule.weight for rule in site.rules], k=1)[0]
        pieces.append(text[cursor : site.start])
        pieces.append(_match_leading_case(text[site.start : site.end], chosen.replace))
        cursor = site.end
        applications[chosen.id] += 1
    pieces.append(text[cursor:])
    result = "".join(pieces)
    return ExpansionResult(
        text=result,
        applications=applications,
        words=count_words(result),
        sites=len(sites),
        applied=sum(applications.values()),
        skipped=skipped,
    )


def expand_text(
    text: str,
    rules: Sequence[Rule],
    rng: random.Random,
    *,
    rate: float,
) -> tuple[str, Counter[str]]:
    """:func:`expand_example` without the telemetry, for callers that only want
    the text and the tally of which rules fired."""
    result = expand_example(text, rules, rng, rate=rate)
    return result.text, result.applications


# ---------------------------------------------------------------------------
# The directory pass
# ---------------------------------------------------------------------------


@dataclass
class ExpansionTally:
    """Running totals behind the sidecar's ``expansion.realised`` block.

    Kept per label and per label mode because that is the DD5 instrument.
    Equality is **not** claimed here and must not be: the classes are made of
    different words, so a class whose lines simply contain fewer matchable
    phrases will take fewer substitutions. What a gap means is "these libraries
    say this signal in different words depending on the label", which is the
    fault the pass exists to reduce -- it is not evidence of a label-aware pass,
    because nothing in the substitution path can see a label.
    """

    words: Counter[str] = field(default_factory=Counter)
    substitutions: Counter[str] = field(default_factory=Counter)
    mode_words: Counter[str] = field(default_factory=Counter)
    mode_substitutions: Counter[str] = field(default_factory=Counter)
    examples: Counter[str] = field(default_factory=Counter)
    clean: Counter[str] = field(default_factory=Counter)
    rules: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    total_words: int = 0
    total_sites: int = 0
    total_applied: int = 0
    changed: int = 0

    def add(self, result: ExpansionResult, *, label: str, label_mode: str, was_clean: bool) -> None:
        self.words[label] += result.words
        self.substitutions[label] += result.applied
        self.mode_words[label_mode] += result.words
        self.mode_substitutions[label_mode] += result.applied
        self.examples[label] += 1
        self.clean[label] += int(was_clean)
        self.rules.update(result.applications)
        self.skipped.update(result.skipped)
        self.total_words += result.words
        self.total_sites += result.sites
        self.total_applied += result.applied
        self.changed += int(bool(result.applied))

    def merge(self, other: ExpansionTally) -> None:
        for name in (
            "words",
            "substitutions",
            "mode_words",
            "mode_substitutions",
            "examples",
            "clean",
            "rules",
            "skipped",
        ):
            getattr(self, name).update(getattr(other, name))
        self.total_words += other.total_words
        self.total_sites += other.total_sites
        self.total_applied += other.total_applied
        self.changed += other.changed

    @staticmethod
    def _rate(edits: int, words: int) -> float:
        return 0.0 if not words else round(100 * edits / words, 4)

    @property
    def substitutions_per_hundred_words(self) -> float:
        return self._rate(self.total_applied, self.total_words)

    def by_label_rates(self) -> dict[str, float]:
        return {label: self._rate(self.substitutions[label], self.words[label]) for label in LABELS}

    def by_label_mode_rates(self) -> dict[str, float]:
        return {
            mode: self._rate(self.mode_substitutions[mode], self.mode_words[mode])
            for mode in LABEL_MODES
        }

    @property
    def largest_by_label_gap(self) -> float:
        """Widest spread in substitution density across the labels present.

        The number worth reading first after a run, and the one whose meaning
        is easiest to get backwards -- see :class:`ExpansionTally`.
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

    @property
    def changed_share(self) -> float:
        """Share of examples that actually differ from their clean twin.

        The denominator of the paired flip rate (DD7): an example no rule
        touched cannot flip, and counting it would only dilute.
        """
        total = sum(self.examples.values())
        return 0.0 if not total else round(self.changed / total, 4)


def build_expansion_stats(
    stats: Mapping[str, object],
    *,
    tally: ExpansionTally,
    texts: Sequence[tuple[str, str, str, str]],
    ruleset: RuleSet,
    source_dir: str,
    seed: int,
    rate: float,
    clean_share: float,
) -> dict:
    """Return the output sidecar: the input's, with two things changed.

    ``token_counts`` is recomputed, because "a fever" -> "a high temperature"
    changes a word count and a sidecar has to describe the file sitting next to
    it. Everything else passes through untouched: ``fragments``,
    ``fragment_counts``, the fold configuration and ``generator_version`` all
    describe the *fragments*, and no fragment was edited. ``generator_version``
    in particular is not bumped -- the three splits of a fold must agree on it
    (``dataset._check_fold_agreement``) and an expanded tree is still that
    generator's output.

    An ``expansion`` block is added. Its presence is the marker that a tree has
    been expanded, and therefore the guard against expanding it twice.
    ``dataset._read_stats`` checks only for the keys it requires, so an extra
    top-level block is additive and safe.
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
                "path": str(ruleset.path),
                "sha256": ruleset.digest,
                "signal": ruleset.signal,
                "count": len(ruleset.rules),
                "by_tier": dict(sorted(Counter(rule.tier for rule in ruleset.rules).items())),
            },
        },
        "realised": {
            # DD5. A gap here is a statement about the libraries, not about the
            # pass: nothing in the substitution path can see a label. Read it
            # as "this signal is said in different words depending on the
            # label", which is the fault being reduced.
            "substitutions_per_hundred_words": {
                "by_label": tally.by_label_rates(),
                "by_label_mode": tally.by_label_mode_rates(),
                "overall": tally.substitutions_per_hundred_words,
                "largest_by_label_gap": tally.largest_by_label_gap,
            },
            "clean_share": {
                "by_label": tally.clean_share(),
                "overall": tally.overall_clean_share,
            },
            "rules": dict(sorted(tally.rules.items())),
            "sites": {
                "found": tally.total_sites,
                "applied": tally.total_applied,
                "skipped": dict(sorted(tally.skipped.items())),
            },
            # The flip rate's denominator (DD7).
            "changed_examples": {
                "count": tally.changed,
                "share": tally.changed_share,
            },
        },
    }
    return output


def check_tree(
    paths: Sequence[Path],
    sidecars: Sequence[Mapping[str, object]],
    *,
    rules_dir: Path | None = None,
) -> dict[str, RuleSet]:
    """Refuse an input tree that cannot be expanded honestly, and load its rules.

    Four checks and one side effect, all of them startup failures. A tree that
    already carries an ``expansion`` block would be expanded twice, compounding
    in a way no rate describes. A tree carrying a ``noise`` block is DD9: both
    passes multiply surface forms, so running them in the same experiment makes
    the result unattributable, and if they are ever combined the order is
    expand-then-noise -- paraphrase first, damage the final surface second. A
    signal with no rule file has nothing to expand *with*, and writing an
    untouched copy of a tree under a name that says "expanded" is the kind of
    silent no-op an arm comparison cannot see. And a tree whose files disagree
    on the fold configuration was half-regenerated.

    The rule files are loaded here rather than later so that every layer of DD6
    has run before the first byte is written.
    """
    if not paths:
        raise ExpansionError("no *.jsonl files found under --in-dir")

    loaded: dict[str, RuleSet] = {}
    for path, stats in zip(paths, sidecars, strict=True):
        if "expansion" in stats:
            raise ExpansionError(
                f"{sidecar_path(path)} already carries an 'expansion' block; expanding an "
                "expanded tree compounds in a way no rate describes"
            )
        if "noise" in stats:
            raise ExpansionError(
                f"{sidecar_path(path)} carries a 'noise' block; expansion and the noise pass "
                "both multiply surface forms, so running them in the same experiment makes the "
                "result unattributable (DD9). Expand the clean tree, then noise the expanded one"
            )
        signal = stats.get("signal")
        if not isinstance(signal, str) or not signal:
            raise ExpansionError(f"{sidecar_path(path)} records no 'signal'")
        if signal not in loaded:
            try:
                loaded[signal] = load_rules(rules_path(signal, rules_dir))
            except ExpansionError as error:
                raise ExpansionError(f"{sidecar_path(path)}: {error}") from None

    for field_name in TREE_AGREEMENT_FIELDS:
        values = {json.dumps(stats.get(field_name), sort_keys=True) for stats in sidecars}
        if len(values) > 1:
            raise ExpansionError(
                f"the sidecars under --in-dir disagree on {field_name!r} "
                f"({', '.join(sorted(values))}); this tree was half-regenerated, and expanding "
                "it would hide that until training time"
            )
    return loaded


def _read_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ExpansionError(f"{path} line {number} is not valid JSON: {error}") from error
    return records


def expand_file(
    in_path: Path,
    out_path: Path,
    *,
    ruleset: RuleSet,
    rate: float,
    seed: int,
    clean_share: float,
    stats: Mapping[str, object] | None = None,
) -> ExpansionTally:
    """Expand one split's JSONL and write it, with its sidecar, to ``out_path``.

    ``example_id``, ``split``, ``labels`` and ``meta`` are copied through
    untouched and the record's key order is
    :data:`~scripts.synthetic_data.noise.RECORD_KEYS`, so a diff against the
    clean tree shows exactly one field changed. That pairing is not a tidiness
    property: it is what lets ``swap_test_split`` put this tree's test split
    under a model trained on the clean one and compute a *paired* flip rate
    (DD1, DD7).
    """
    stats = read_sidecar(in_path) if stats is None else stats
    tally = ExpansionTally()
    rows: list[tuple[str, str, str, str]] = []
    records = _read_records(in_path)

    for record in records:
        rng = example_rng(seed, record["example_id"])
        # First draw of the example, before the text is looked at, so the clean
        # share cannot depend on anything about the example (DD3).
        was_clean = rng.random() < clean_share
        if was_clean:
            result = ExpansionResult(
                text=record["text"],
                applications=Counter(),
                words=count_words(record["text"]),
                sites=0,
                applied=0,
                skipped=Counter(),
            )
        else:
            result = expand_example(record["text"], ruleset.rules, rng, rate=rate)
        record["text"] = result.text
        meta = record.get("meta", {})
        label = label_name(record.get("labels", {}).get(ruleset.signal))
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
        ruleset=ruleset,
        source_dir=str(in_path.parent),
        seed=seed,
        rate=rate,
        clean_share=clean_share,
    )
    with sidecar_path(out_path).open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(output_stats, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    return tally


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
) -> ExpansionTally:
    """Expand a whole fold tree, filenames and all, into ``out_dir``.

    Whole tree in, whole tree out. ``dataset.FOLD_FILENAME`` is how
    ``scripts/encoder_training/`` finds a fold at all, so every file keeps its
    name and anything that is neither a dataset nor a sidecar is copied through
    byte-for-byte: the output tree is a drop-in ``--data-dir`` or ``--test-dir``.
    """
    try:
        check_directories(
            in_dir, out_dir, force=force, root=GENERATED_ROOT if root is None else root
        )
    except NoiseError as error:
        raise ExpansionError(str(error)) from None

    paths = sorted(in_dir.rglob("*.jsonl"))
    try:
        sidecars = [read_sidecar(path) for path in paths]
    except NoiseError as error:
        raise ExpansionError(str(error)) from None
    rulesets = check_tree(paths, sidecars, rules_dir=rules_dir)

    known = set(paths) | {sidecar_path(path) for path in paths}
    total = ExpansionTally()
    for path, stats in zip(paths, sidecars, strict=True):
        target = out_dir / path.relative_to(in_dir)
        total.merge(
            expand_file(
                path,
                target,
                ruleset=rulesets[stats["signal"]],
                rate=rate,
                seed=seed,
                clean_share=clean_share,
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
        description=(
            "Write a lexically expanded copy of a generated fold tree, ids and filenames "
            "intact, so each example is paired with its clean original."
        ),
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
        help="probability that any one match site is rewritten, Bernoulli per site rather than "
        "per example (DD3). Required rather than defaulted: there is no rate that is obviously "
        "right, and the sweep is the point",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--clean-share",
        type=_share,
        default=DEFAULT_CLEAN_SHARE,
        help="share of examples left completely untouched. The point is to shift the vocabulary "
        "distribution rather than to replace it: a tree in which every 'fever' became a "
        "'temperature' would have swapped one perfect association for another",
    )
    parser.add_argument(
        "--rules-dir",
        type=Path,
        default=RULES_ROOT,
        help=f"directory holding '<signal>.rules.json' (default: {RULES_ROOT}). Deliberately "
        "outside data/synthetic/, which holds nothing but the libraries and the manifest",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write into a non-empty --out-dir",
    )
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
    except ExpansionError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # The numbers worth seeing without opening a sidecar: how much text moved,
    # whether it moved evenly across the labels, and how big the paired flip
    # rate's denominator is going to be.
    print(
        f"wrote {sum(tally.examples.values())} examples to {args.out_dir} "
        f"(substitutions/100 words={tally.substitutions_per_hundred_words}, "
        f"largest by-label gap={tally.largest_by_label_gap}, "
        f"changed examples={tally.changed} ({tally.changed_share}))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
