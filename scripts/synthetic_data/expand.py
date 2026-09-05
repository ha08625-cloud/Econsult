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
from dataclasses import replace as dataclass_replace
from pathlib import Path

from .lint import (
    SIGNAL_LEXICONS,
    LexiconHit,
    cross_signal_cells,
    filler_lexicon_hits,
    lexicon_matches,
)
from .manifest import Fragment, ManifestError, load_fragments
from .noise import (
    FIRST_PERSON,
    GENERATED_ROOT,
    LABEL_MODES,
    LABELS,
    PERSON_CLASSES,
    RECORD_KEYS,
    STRUCTURAL_FROZEN,
    THIRD_PARTY,
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

#: Where swap-class files live, one per group, named ``<group>.classes.json``.
#:
#: A subdirectory of :data:`RULES_ROOT` rather than a sibling of the rule
#: files, because the two formats are selected independently at run time and a
#: glob over one must never pick up the other.
CLASSES_ROOT = RULES_ROOT / "classes"

#: Every key a swap class may carry. Closed, exactly as :data:`RULE_KEYS` is
#: and for a sharper version of the same reason: one class invariant now stands
#: for dozens of generated rules, so a misspelt key removes the safety argument
#: for all of them at once rather than for one.
CLASS_REQUIRED_KEYS = frozenset(
    {"id", "gender", "life_stage", "number", "person", "tier", "members", "invariant"}
)
CLASS_KEYS = CLASS_REQUIRED_KEYS

#: Top-level keys of a class file. Closed for the same reason.
CLASS_FILE_KEYS = frozenset({"group", "classes"})

#: The closed vocabularies the four declaration keys draw from (DD11).
#:
#: They are **declarations, not machinery**: nothing downstream reads them, and
#: the loader checks only that each is a known word and that no member appears
#: in two classes of a group. The format cannot check agreement -- that "my
#: kids were" survives ``kids -> child`` is a human's judgement -- and DD11 is
#: explicit that it never will. What they buy is a reviewer's job made small
#: and concrete: every member of one class must answer to the same four words,
#: so a list is checkable by reading it rather than by imagining the sentences
#: it lands in.
#:
#: ``neutral`` is a person whose gender the class does not fix; ``none`` is a
#: class whose members are not people at all (weekdays, places), and the same
#: distinction is why ``life_stage`` and ``person`` carry ``none`` too.
GENDERS = ("female", "male", "neutral", "none")
LIFE_STAGES = ("adult", "elder", "child", "none")
NUMBERS = ("singular", "plural")
PERSONS = ("first-person", "third-party", "none")

#: A class smaller than this generates nothing; a class larger than it stops
#: being reviewable, in both the pair count (13 members is 156 ordered pairs)
#: and the number of sentences a reader has to hold in their head at once.
MIN_CLASS_MEMBERS = 2
MAX_CLASS_MEMBERS = 12

#: Floor on a class invariant, in characters. Twice the floor the committed
#: rule files are held to, because of that concentration of risk: a rule
#: invariant answers for one swap and a class invariant answers for every
#: ordered pair the list generates (DD6 layer 1).
MIN_CLASS_INVARIANT = 120

#: Vowels for the multi-word member check (v2 review, F6). A vowel-initial
#: member landing where the library wrote "a" produces "a other half", and no
#: mechanical layer sees it: neither a structural token nor a signal lexicon
#: has moved.
#:
#: The check refuses a vowel-initial member only when it is **multi-word**,
#: which is the line the plan draws and is a floor rather than a fix. A
#: single vowel-initial word ("aunt", "uncle", "eldest") has the same failure
#: mode and the loader does not catch it; what stands behind those is the
#: class invariant and the dry-run read (Task 6), the same as for every other
#: agreement question the format cannot express (DD11).
#:
#: Orthographic, so "hour" passes and "unit" does not. Both are wrong about
#: English and neither matters at this floor.
_VOWELS = frozenset("aeiou")

#: The two tiers this pass will run (DD4). Tier A is orthography and
#: contraction -- it cannot change which word a token is. Tier B is signal
#: vocabulary -- a real risk, and the one the three layers exist to bound.
#: Tier C (aspect and opener rewrites) needs a rule scoped to a *library*,
#: which post-processing cannot express, and is out of scope.
TIERS = ("A", "B")

#: What ``--rules`` selects. ``signal`` is DD5's ``v1`` arm and is byte-for-byte
#: what the 2026-09-04 anchor ran; ``classes`` is the swap classes alone;
#: ``both`` concatenates them, which is the decision arm.
RULE_KINDS = ("signal", "classes", "both")


def selects_signal_rules(rule_kinds: str) -> bool:
    """Whether ``--rules`` asks for the hand-written per-signal rule file."""
    return rule_kinds in ("signal", "both")


def selects_classes(rule_kinds: str) -> bool:
    """Whether ``--rules`` asks for the swap classes."""
    return rule_kinds in ("classes", "both")


#: Share of examples the pass leaves untouched.
#:
#: Same default as the noise pass, and for a related reason: the point is to
#: shift the vocabulary distribution, not to replace it. A tree in which every
#: ``fever`` became a ``temperature`` would have swapped one perfect
#: association for another.
DEFAULT_CLEAN_SHARE = 0.25

#: Structural tokens, folded once, for :func:`structural_sequence`. The two
#: person-class markers are members because a class-generated rule's sequence
#: is built from them: they are what "my mum" and "my sister" have in common
#: and what "my mum" and "I" do not (DD6a).
_STRUCTURAL = frozenset(fold_token(word) for word in STRUCTURAL_FROZEN) | {
    FIRST_PERSON,
    THIRD_PARTY,
}

#: Longest :data:`~scripts.synthetic_data.noise.PERSON_CLASSES` key, in words.
#: Keys are matched longest-first so that a multi-word member ("little one")
#: collapses to a single marker rather than to its two unmapped words.
_PERSON_CLASS_MAX_WORDS = max(len(key.split()) for key in PERSON_CLASSES)

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
    #: ``None`` for a rule read from a ``*.rules.json`` file; the class id for
    #: one the swap-class loader generated. It is the *only* thing that
    #: relaxes layer 2 onto person classes (DD6a), and keeping the relaxation
    #: on the rule rather than in :func:`_check_structural` is what stops a
    #: hand-written file borrowing it (v2 review, F3).
    origin: str | None = None

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

    @property
    def source(self) -> RuleSource:
        """This file as the sidecar records it."""
        return RuleSource(
            path=self.path,
            digest=self.digest,
            kind="rules",
            name=self.signal,
            signal=self.signal,
            rules=self.rules,
        )


@dataclass(frozen=True)
class RuleSource:
    """One *file* a run's rules came from.

    A run no longer has "the rule file": an arm is a selection over a per-signal
    ``*.rules.json`` and any number of ``*.classes.json`` groups (DD5), and the
    rules of several files are concatenated before the pass sees them. What
    survives that concatenation -- and what a report needs in order to be
    reproducible at all -- is the *sources*, one entry per file with its digest.

    ``name`` is the signal for a rule file and the group for a class file, and
    is what a log line or a dry-run header prints. ``signal`` is deliberately
    ``None`` for a class file rather than absent: a swap class belongs to no
    signal (DD2), and a null there says so where a missing key would only look
    like an older sidecar.
    """

    path: Path
    digest: str
    kind: str
    name: str
    signal: str | None
    rules: tuple[Rule, ...]

    def as_dict(self) -> dict:
        """The sidecar entry. Ordered as a reader would want to read it."""
        return {
            "path": str(self.path),
            "sha256": self.digest,
            "kind": self.kind,
            "signal": self.signal,
            "count": len(self.rules),
            "by_tier": dict(sorted(Counter(rule.tier for rule in self.rules).items())),
        }

    @property
    def label(self) -> str:
        """``fever_present (rules)`` or ``referent (classes)``."""
        return f"{self.name} ({self.kind})"


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


def _person_classes(words: Sequence[str]) -> list[str]:
    """Replace every :data:`PERSON_CLASSES` member in ``words`` with its marker.

    Longest match wins, so "little one" becomes one :data:`THIRD_PARTY` and not
    two unmapped words. No key begins with a structural token, so a match can
    never swallow one: the longest keys are "little one" and "other half", and
    neither "little" nor "other" is frozen.
    """
    normalised: list[str] = []
    index = 0
    while index < len(words):
        span = min(_PERSON_CLASS_MAX_WORDS, len(words) - index)
        for length in range(span, 0, -1):
            marker = PERSON_CLASSES.get(" ".join(words[index : index + length]))
            if marker is not None:
                normalised.append(marker)
                index += length
                break
        else:
            normalised.append(words[index])
            index += 1
    return normalised


def structural_sequence(phrase: str, *, person_classes: bool = False) -> tuple[str, ...]:
    """The :data:`STRUCTURAL_FROZEN` tokens of ``phrase``, in order.

    Contractions are expanded first, so ``haven't`` and ``have not`` produce
    the same sequence. This is DD6 layer 2's whole comparison: negation decides
    ``true`` from ``false``, person and tense decide the null axes, and
    modality separates a hard-case ``null`` from an assertion, so a swap that
    inserts "not", drops "my" or turns "had" into "have" has changed the label
    whatever its author intended.

    With ``person_classes``, every
    :data:`~scripts.synthetic_data.noise.PERSON_CLASSES` member is first
    normalised to its class marker, so the comparison asks *whose symptom is
    this* rather than *which word names them* -- which is what lets
    ``mum -> sister`` load while ``mum -> I`` still does not (DD6a). The
    default is the behaviour every hand-written rule file has always had, byte
    for byte, and only :attr:`Rule.origin` turns it on.

    Order matters: contractions are expanded **before** the map is consulted,
    so ``I've -> I have`` still produces ``('<first-person>', 'have')`` on both
    sides and the Tier A rules layer 2 exists to carry are not newly refused.
    Mapping then runs before the :data:`_STRUCTURAL` filter, because the map's
    whole job is to decide what survives that filter.
    """
    words: list[str] = []
    for token in split_words(phrase):
        folded = fold_token(token.word)
        if not folded:
            continue
        words.extend(_CONTRACTIONS.get(folded, folded).split())
    if person_classes:
        words = _person_classes(words)
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
    """Layer 2 of the load check: DD6's structural-token invariance.

    A rule the swap-class loader generated is compared on person *class* rather
    than on the literal person tokens (DD6a); a rule read from a
    ``*.rules.json`` file is not, and that asymmetry is the point. The eleven
    referent nouns in :data:`STRUCTURAL_FROZEN` are what a swap class exists to
    move, and they are also what a hand-written rule must never move silently.
    """
    generated = rule.origin is not None
    before = structural_sequence(rule.find, person_classes=generated)
    after = structural_sequence(rule.replace, person_classes=generated)
    if before != after:
        source = f" (class {rule.origin!r})" if generated else ""
        raise ExpansionError(
            f"rule {rule.id!r}{source}: structural-token invariance (DD6 layer 2). "
            f"{rule.find!r} carries {before or '()'} and {rule.replace!r} carries "
            f"{after or '()'}. Those tokens are negation, person, tense and modality -- the "
            "swap changes the label, whatever it was meant to change"
        )


def _check_lexicons(rule: Rule, signal: str | None) -> None:
    """Layer 3 of the load check: DD6's signal-lexicon invariance.

    For a rule read from a ``*.rules.json`` file, ``signal`` is that file's
    signal and the check has two halves. The rule may not change whether its
    phrase reads as **its own** signal -- ``fever -> temperature`` is a swap
    inside the lexicon, ``fever -> headache`` walks a decisive line into saying
    nothing about fever. And it may not introduce **another** signal's language
    that ``find`` did not have, which is the one thing re-running the whole
    lint over the expanded tree was ever for, done per-rule: cheaper, and
    precise about which rule is at fault.

    A class-generated rule has **no signal** -- that is DD2, and it is what
    makes one class file worth thirteen reviews across seven libraries -- so
    ``signal`` is ``None`` and the check is strictly stronger instead: the set
    of matched terms must be unchanged for *every* signal. There is no "own"
    lexicon to swap inside, so a class that moves signal language at all is a
    class doing a signal rule file's job in a file no signal reviewed.
    """
    if signal is None:
        for other in sorted(SIGNAL_LEXICONS):
            before = set(lexicon_matches(rule.find, other))
            after = set(lexicon_matches(rule.replace, other))
            if before != after:
                moved = ", ".join(sorted(before ^ after))
                raise ExpansionError(
                    f"rule {rule.id!r} (class {rule.origin!r}): signal-lexicon invariance "
                    f"(DD6 layer 3). {rule.find!r} -> {rule.replace!r} moves {other} language "
                    f"({moved}). A swap class belongs to no signal, so it may not move any "
                    "signal's vocabulary; that swap belongs in that signal's rule file"
                )
        return
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
# The swap-class format
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SwapClass:
    """One hand-written list of interchangeable members, and its invariant.

    The whole point of the format is arithmetic: a list of eight members is
    one review and fifty-six ordered pairs, and because the members belong to
    no signal those pairs apply to every library rather than to one (DD2,
    DD3). Thirteen such lists are the ticket.

    ``gender``, ``life_stage``, ``number`` and ``person`` are declarations. The
    loader checks they are known words and that no member sits in two classes
    of a group; nothing checks that the members *are* what they say, and
    nothing can -- see :data:`GENDERS`. They exist so a reviewer reads one list
    against one sentence ("my X was up all night") instead of reading fifty-six
    pairs.

    ``invariant`` is DD6 layer 1 for every pair the class generates, which is
    why it is held to twice a rule's floor.
    """

    id: str
    gender: str
    life_stage: str
    number: str
    person: str
    tier: str
    members: tuple[str, ...]
    invariant: str

    def rules(self) -> tuple[Rule, ...]:
        """Every ordered pair of distinct members, as generated rules.

        Members are paired in sorted order rather than authored order, so the
        rule sequence is a function of the *set* of members and reordering the
        JSON list cannot move a rule id or reorder the pass's draws.
        """
        ordered = sorted(self.members)
        return tuple(
            Rule(
                id=_class_rule_id(self.id, find, replace),
                tier=self.tier,
                find=find,
                replace=replace,
                invariant=self.invariant,
                weight=1.0,
                origin=self.id,
            )
            for find in ordered
            for replace in ordered
            if find != replace
        )


@dataclass(frozen=True)
class ClassSet:
    """One group's classes, the rules they expand to, and its provenance.

    ``path`` and ``digest`` are ``None`` for a set parsed from a document in
    memory, which is what lets the tests put a malformed class in front of
    every check without a disk; :func:`load_classes` fills them in.
    """

    group: str
    classes: tuple[SwapClass, ...]
    rules: tuple[Rule, ...]
    path: Path | None = None
    digest: str | None = None

    @property
    def source(self) -> RuleSource:
        """This file as the sidecar records it.

        Only meaningful for a set that came off a disk: a set parsed in memory
        has no path and no digest to record, and asking for its provenance is
        a bug rather than a degraded answer.
        """
        if self.path is None or self.digest is None:
            raise ExpansionError(
                f"class group {self.group!r} was parsed from memory and has no path or digest "
                "to record; only a loaded class file can be a rule source"
            )
        return RuleSource(
            path=self.path,
            digest=self.digest,
            kind="classes",
            name=self.group,
            signal=None,
            rules=self.rules,
        )


def _class_rule_id(class_id: str, find: str, replace: str) -> str:
    """The deterministic id of one generated rule.

    Spaces become underscores so that a member like "little one" leaves an id
    that reads as a single token in a log line, a sidecar and a test failure.
    """
    return f"{class_id}:{find}->{replace}".replace(" ", "_")


def _check_class_shape(raw: Mapping[str, object], group: str, index: int) -> SwapClass:
    """Turn one JSON object into a :class:`SwapClass`, or say why it is not one."""
    where = f"class {index}"
    keys = set(raw)
    unknown = keys - CLASS_KEYS
    if unknown:
        raise ExpansionError(
            f"{where}: unknown key(s) {', '.join(sorted(unknown))}; a class carries only "
            f"{', '.join(sorted(CLASS_KEYS))} and the key set is closed, so a misspelt key is a "
            "silently ignored declaration rather than a comment"
        )
    missing = CLASS_REQUIRED_KEYS - keys
    if missing:
        raise ExpansionError(f"{where}: missing required key(s) {', '.join(sorted(missing))}")

    for name in ("id", "gender", "life_stage", "number", "person", "tier", "invariant"):
        value = raw[name]
        if not isinstance(value, str) or not value.strip():
            raise ExpansionError(f"{where}: {name!r} must be a non-empty string, got {value!r}")

    class_id = str(raw["id"]).strip()
    where = f"class {class_id!r}"
    if not class_id.startswith(f"{group}."):
        raise ExpansionError(
            f"{where}: a class id is '<group>.<name>', so this one must start with "
            f"{group + '.'!r}. The id is carried on every rule the class generates and is the "
            "only provenance a reader of the sidecar gets"
        )

    for name, vocabulary in (
        ("gender", GENDERS),
        ("life_stage", LIFE_STAGES),
        ("number", NUMBERS),
        ("person", PERSONS),
    ):
        value = str(raw[name]).strip()
        if value not in vocabulary:
            raise ExpansionError(
                f"{where}: {name} {value!r} is not one of {', '.join(vocabulary)}. The "
                "vocabularies are closed so that a declaration is a word a reviewer can check "
                "the whole list against, not free text"
            )

    tier = str(raw["tier"]).strip()
    if tier not in TIERS:
        raise ExpansionError(f"{where}: tier {tier!r} is not one of {', '.join(TIERS)}")

    invariant = str(raw["invariant"]).strip()
    if len(invariant) < MIN_CLASS_INVARIANT:
        raise ExpansionError(
            f"{where}: invariant is {len(invariant)} characters and the floor is "
            f"{MIN_CLASS_INVARIANT}. It is the declared invariant for every ordered pair this "
            "class generates, and after DD6a no mechanical layer stands behind it -- say what "
            "makes these members interchangeable and in what sentence you checked it"
        )

    raw_members = raw["members"]
    if not isinstance(raw_members, list):
        raise ExpansionError(f"{where}: 'members' must be a list, got {raw_members!r}")
    members: list[str] = []
    for member in raw_members:
        if not isinstance(member, str) or not member.strip():
            raise ExpansionError(f"{where}: member {member!r} must be a non-empty string")
        if member != member.strip():
            raise ExpansionError(f"{where}: member {member!r} has leading or trailing whitespace")
        if not _WORD_CHARACTER.match(member[0]) or not _WORD_CHARACTER.match(member[-1]):
            raise ExpansionError(
                f"{where}: member {member!r} must start and end on a word character, or the "
                "whole-word boundary around a match site means nothing"
            )
        if " " in member and member[0].lower() in _VOWELS:
            raise ExpansionError(
                f"{where}: member {member!r} is vowel-initial and multi-word. Landing it where "
                "the library wrote 'a' produces 'a other half', and neither mechanical layer "
                "sees it; write it as a determiner-anchored swap in a rule file instead"
            )
        members.append(member)

    if not MIN_CLASS_MEMBERS <= len(members) <= MAX_CLASS_MEMBERS:
        raise ExpansionError(
            f"{where}: {len(members)} member(s); a class holds between {MIN_CLASS_MEMBERS} and "
            f"{MAX_CLASS_MEMBERS}. Below the floor it generates no pairs at all; above the "
            "ceiling the pair count and the review both stop being something a person finishes"
        )
    duplicates = sorted(
        {
            folded
            for folded in (fold_haystack(member) for member in members)
            if [fold_haystack(other) for other in members].count(folded) > 1
        }
    )
    if duplicates:
        raise ExpansionError(
            f"{where}: member(s) {', '.join(duplicates)} listed more than once; a repeated "
            "member is a rule that would be generated twice and a list nobody has read"
        )

    return SwapClass(
        id=class_id,
        gender=str(raw["gender"]).strip(),
        life_stage=str(raw["life_stage"]).strip(),
        number=str(raw["number"]).strip(),
        person=str(raw["person"]).strip(),
        tier=tier,
        members=tuple(members),
        invariant=invariant,
    )


def parse_classes(payload: object, *, source: str) -> ClassSet:
    """Validate a loaded class document, expand it, and return a :class:`ClassSet`.

    File-free, so the tests can put a malformed document in front of every
    check without touching a disk.

    Generation is a convenience for the author and not a hole in the safety
    argument (DD3): every ordered pair the classes expand to runs the same
    per-rule layers a hand-written rule does -- layer 1 whole-word matchability,
    layer 2 structural invariance (on person *class*, because these rules carry
    an ``origin``), layer 3 signal-lexicon invariance in its stronger
    signal-agnostic form.
    """
    if not isinstance(payload, dict):
        raise ExpansionError(f"{source} is not a JSON object")
    unknown = set(payload) - CLASS_FILE_KEYS
    if unknown:
        raise ExpansionError(f"{source}: unknown top-level key(s) {', '.join(sorted(unknown))}")
    group = payload.get("group")
    if not isinstance(group, str) or not group.strip():
        raise ExpansionError(f"{source}: 'group' must be a non-empty string, got {group!r}")
    group = group.strip()
    raw_classes = payload.get("classes")
    if not isinstance(raw_classes, list) or not raw_classes:
        raise ExpansionError(f"{source}: 'classes' must be a non-empty list")

    classes: list[SwapClass] = []
    rules: list[Rule] = []
    seen_ids: set[str] = set()
    #: Folded member -> the class that already claimed it. A word in two
    #: classes of one group is a swap that escapes its own declared gender,
    #: life stage or number: "sister" in both the female and the neutral class
    #: generates "sister -> brother" through the neutral list (DD11).
    seen_members: dict[str, str] = {}
    for index, raw in enumerate(raw_classes):
        if not isinstance(raw, dict):
            raise ExpansionError(f"{source}: class {index} is not a JSON object")
        try:
            swap_class = _check_class_shape(raw, group, index)
            if swap_class.id in seen_ids:
                raise ExpansionError(f"class {swap_class.id!r}: duplicate id")
            seen_ids.add(swap_class.id)
            for member in swap_class.members:
                folded = fold_haystack(member)
                owner = seen_members.get(folded)
                if owner is not None:
                    raise ExpansionError(
                        f"class {swap_class.id!r}: member {member!r} is already in class "
                        f"{owner!r}. A word in two classes of one group is a pair that escapes "
                        "the declaration both classes make about it"
                    )
                seen_members[folded] = swap_class.id
            for rule in swap_class.rules():
                _check_matchable(rule)
                _check_structural(rule)
                _check_lexicons(rule, None)
                rules.append(rule)
        except ExpansionError as error:
            raise ExpansionError(f"{source}: {error}") from None
        classes.append(swap_class)

    return ClassSet(group=group, classes=tuple(classes), rules=tuple(rules))


def load_classes(path: Path) -> ClassSet:
    """Load and validate one group's class file.

    Every layer runs here, before the pass has opened a single dataset, for the
    reason :func:`load_rules` gives: a class file is authored by a human and
    the rejection message is the whole of that person's feedback loop.
    """
    if not path.is_file():
        raise ExpansionError(f"no class file at {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExpansionError(f"{path} is not valid JSON: {error}") from error
    parsed = parse_classes(payload, source=str(path))
    expected = path.name.removesuffix(".classes.json")
    if parsed.group != expected:
        raise ExpansionError(
            f"{path}: declares group {parsed.group!r} but is named for {expected!r}; the "
            "filename is how an arm selects a group, so the two disagreeing means one of them "
            "is silently not what was run"
        )
    return dataclass_replace(parsed, path=path, digest=hashlib.sha256(raw).hexdigest())


def classes_path(group: str, classes_dir: Path | None = None) -> Path:
    """Where ``group``'s class file lives."""
    root = CLASSES_ROOT if classes_dir is None else classes_dir
    return root / f"{group}.classes.json"


def discover_class_groups(classes_dir: Path | None = None) -> tuple[str, ...]:
    """Every group with a file in ``classes_dir``, sorted.

    The default of ``--class-groups`` and therefore of an arm that names none:
    whatever is committed. Sorted so that adding a group cannot reorder the
    rules of the groups already there.
    """
    root = CLASSES_ROOT if classes_dir is None else classes_dir
    if not root.is_dir():
        return ()
    return tuple(
        sorted(path.name.removesuffix(".classes.json") for path in root.glob("*.classes.json"))
    )


def load_class_groups(
    groups: Sequence[str], classes_dir: Path | None = None
) -> tuple[ClassSet, ...]:
    """Load several groups, refusing a class id or a member shared between them.

    Uniqueness inside a group is :func:`parse_classes`'s job; this is the same
    check one level up, because two files are exactly where a member gets
    copied and forgotten.
    """
    loaded: list[ClassSet] = []
    seen_ids: dict[str, Path] = {}
    seen_members: dict[str, str] = {}
    for group in groups:
        class_set = load_classes(classes_path(group, classes_dir))
        for swap_class in class_set.classes:
            first = seen_ids.get(swap_class.id)
            if first is not None:
                raise ExpansionError(
                    f"class {swap_class.id!r} is declared in both {first} and {class_set.path}"
                )
            seen_ids[swap_class.id] = class_set.path or Path(group)
            for member in swap_class.members:
                folded = fold_haystack(member)
                owner = seen_members.get(folded)
                if owner is not None:
                    raise ExpansionError(
                        f"{class_set.path}: member {member!r} of class {swap_class.id!r} is "
                        f"already in class {owner!r}"
                    )
                seen_members[folded] = swap_class.id
        loaded.append(class_set)
    return tuple(loaded)


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
    it did, and ``skipped`` why the rest did not. Three reasons exist now: the
    per-site rate coin, ``class_collision`` where injectivity emptied the
    candidate list, and ``memo`` where a repeat of an already-decided source
    word inherited a decision of "leave it alone" (DD12). Every site lands in
    exactly one of ``applied`` and ``skipped``, so the two still add to
    ``sites``.

    ``memoised`` counts the sites the memo decided either way -- applied and
    skipped both -- because that number is also the size of the bug DD12
    prevents: without the memo each of those sites would have drawn its own
    coin and its own replacement, and one person in one example would have
    become two.
    """

    text: str
    applications: Counter[str]
    words: int
    sites: int
    applied: int
    skipped: Counter[str]
    memoised: int = 0


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

    **Class-generated rules take a narrower path** (DD12, v2 review F7), because
    per-site independence is right for a word and wrong for a person. Two things
    change, and both are gated on ``origin`` rather than on a flag so that a
    fever-only rule set walks the code below byte for byte -- DD5's ``v1`` arm is
    the 2026-09-04 anchor and an anchor that does not reproduce is not one:

    * **The decision is memoised, not the target.** The rate coin fires per site
      and *before* the substitution, so memoising only the replacement would
      still produce "my sister ... my wife" whenever the second site lost its
      coin. Once a source word has been drawn for in an example, every later
      occurrence of it takes the same outcome -- substituted, with the same
      replacement, or left alone -- and spends no coin of its own.
    * **Targets are drawn injectively within a class.** Keying on the source
      does not stop two sources collapsing onto one target: "my wife and my
      sister" with ``wife -> sister`` firing gives "my sister and my sister". A
      candidate whose replacement is already committed in this example, or is
      already in the source text as another member of the same class, is
      excluded before the weighted draw; if that empties the list the site is
      skipped as a ``class_collision``.

    Injectivity is scoped to the **class**, not to the rule set: "Monday and
    again on Tuesday" both landing on "Friday" is the same fault as the referent
    one, while ``fever -> temperature`` firing three times in a line is not a
    fault at all.

    Two deliberate conservatisms in the exclusion set. A member present in the
    source *stays* blocked even if this pass replaces it, so "my wife and my
    sister" will not reuse "wife" after moving it -- over-blocking costs a
    substitution and under-blocking costs a mislabelled line. And a site is on
    the class path only if **every** candidate rule at it carries an ``origin``;
    a site where a hand-written rule and a class rule share a ``find`` verbatim
    keeps today's path, because the hand-written rule is not a class member and
    excluding it on a class's behalf would be the loader's job, not this one's.
    """
    sites = match_sites(text, rules)
    haystack = fold_haystack(text)

    #: Per class id, the folded replacements that are no longer available: every
    #: member of that class already standing in the source text, plus every
    #: replacement committed as the pass walks left to right.
    blocked: dict[str, set[str]] = {}
    for site in sites:
        folded = haystack[site.start : site.end]
        for candidate in site.rules:
            if candidate.origin is not None:
                blocked.setdefault(candidate.origin, set()).add(folded)

    #: The outcome already drawn for a folded source word in *this* example.
    #: A local, so the key needs no example id and no leak is possible.
    memo: dict[str, Rule | None] = {}
    memoised = 0

    applications: Counter[str] = Counter()
    skipped: Counter[str] = Counter()
    pieces: list[str] = []
    cursor = 0
    for site in sites:
        from_class = all(candidate.origin is not None for candidate in site.rules)
        folded = haystack[site.start : site.end]
        if from_class and folded in memo:
            chosen = memo[folded]
            memoised += 1
            if chosen is None:
                skipped["memo"] += 1
                continue
        else:
            if rng.random() >= rate:
                if from_class:
                    memo[folded] = None
                skipped["rate_coin"] += 1
                continue
            candidates = site.rules
            if from_class:
                candidates = tuple(
                    candidate
                    for candidate in site.rules
                    if fold_haystack(candidate.replace) not in blocked.get(candidate.origin, ())
                )
                if not candidates:
                    memo[folded] = None
                    skipped["class_collision"] += 1
                    continue
            chosen = rng.choices(
                candidates, weights=[candidate.weight for candidate in candidates], k=1
            )[0]
            if from_class:
                memo[folded] = chosen
        if chosen.origin is not None:
            blocked.setdefault(chosen.origin, set()).add(fold_haystack(chosen.replace))
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
        memoised=memoised,
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
    total_memoised: int = 0
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
        self.total_memoised += result.memoised
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
        self.total_memoised += other.total_memoised
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
    sources: Sequence[RuleSource],
    class_groups: Sequence[str],
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
            "class_groups": list(class_groups),
            # One entry per *file*, not one block for "the" rule file. An arm is
            # a selection over several files (DD5) whose rules are concatenated
            # before the pass sees them, and the digests are the only thing that
            # survives the concatenation -- without them --rate and --seed
            # reproduce a tree only in combination with whatever happened to be
            # on disk, and the files are hand-edited between runs.
            "rule_sources": [source.as_dict() for source in sources],
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
                # DD12 asks for this one because it is also the size of the bug
                # the memo prevents: every one of these sites would otherwise
                # have drawn independently of the site that named the same
                # person or the same day earlier in the line.
                "memoised": tally.total_memoised,
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


@dataclass(frozen=True)
class TreeRules:
    """The rules one run will apply, and where they came from.

    ``by_signal`` is what the pass needs -- one flat tuple per signal, the
    signal's own hand-written rules followed by every selected class rule --
    and it is deliberately *not* keyed by file: :func:`match_sites` prefers the
    longest needle and breaks a tie by weight, so a class rule and a
    hand-written rule matching the same site compete on equal terms and there
    is no sense in which one file's rules run "first".

    ``sources`` is what the sidecar records, because that competition is
    exactly what destroys the old ``expansion.requested.rules`` block's
    one-file-per-run assumption: after the concatenation there is nothing left
    to point a digest at except the files themselves.
    """

    by_signal: dict[str, tuple[Rule, ...]]
    sources: tuple[RuleSource, ...]
    class_groups: tuple[str, ...]

    def sources_for(self, signal: str) -> tuple[RuleSource, ...]:
        """The files whose rules actually reached ``signal``.

        A tree of one signal is the usual case and there the answer is every
        source; a merged tree is not, and recording another signal's rule file
        in this signal's sidecar would say a file was applied that never was.
        """
        return tuple(
            source for source in self.sources if source.signal is None or source.signal == signal
        )


def _selected_class_sets(
    rule_kinds: str,
    *,
    classes_dir: Path | None,
    class_groups: Sequence[str] | None,
) -> tuple[ClassSet, ...]:
    """Load the class files an arm selects, or none if it selects none.

    A *named* group with no file on disk is fatal, because a named group that
    is not there is a typo and never a state -- and naming them is how DD5's
    ``classes`` and ``combined`` arms are actually invoked, so that is where
    the strictness is worth having. Discovery finding nothing is not fatal
    here: the caller decides what an empty selection means, and
    :func:`check_tree`'s zero-rules check is what stops it becoming a silent
    no-op.
    """
    if not selects_classes(rule_kinds):
        return ()
    if class_groups is None:
        groups = discover_class_groups(classes_dir)
    else:
        groups = tuple(class_groups)
        if not groups:
            raise ExpansionError("--class-groups was given no groups")
    return load_class_groups(groups, classes_dir)


def check_tree(
    paths: Sequence[Path],
    sidecars: Sequence[Mapping[str, object]],
    *,
    rules_dir: Path | None = None,
    classes_dir: Path | None = None,
    rule_kinds: str = "both",
    class_groups: Sequence[str] | None = None,
) -> TreeRules:
    """Refuse an input tree that cannot be expanded honestly, and load its rules.

    Four checks and one side effect, all of them startup failures. A tree that
    already carries an ``expansion`` block would be expanded twice, compounding
    in a way no rate describes. A tree carrying a ``noise`` block is DD9: both
    passes multiply surface forms, so running them in the same experiment makes
    the result unattributable, and if they are ever combined the order is
    expand-then-noise -- paraphrase first, damage the final surface second. A
    signal that ends up with **no rules at all** has nothing to expand *with*,
    and writing an untouched copy of a tree under a name that says "expanded"
    is the kind of silent no-op an arm comparison cannot see. And a tree whose
    files disagree on the fold configuration was half-regenerated.

    ``rule_kinds`` is DD5's arm selection. A missing ``<signal>.rules.json`` is
    fatal only when ``signal`` is selected -- a classes-only arm has no use for
    one and requiring it would tie a signal-agnostic pass back to the one
    signal that happens to have a rule file. The zero-rules check is what stops
    that permissiveness becoming a no-op: it asks about the *result* of the
    selection rather than about any one file.

    Every file is loaded here rather than later so that every layer of DD6 has
    run before the first byte is written.
    """
    if rule_kinds not in RULE_KINDS:
        raise ExpansionError(f"--rules must be one of {', '.join(RULE_KINDS)}, got {rule_kinds!r}")
    if not paths:
        raise ExpansionError("no *.jsonl files found under --in-dir")

    class_sets = _selected_class_sets(
        rule_kinds, classes_dir=classes_dir, class_groups=class_groups
    )
    class_rules = tuple(rule for class_set in class_sets for rule in class_set.rules)

    signals: list[str] = []
    rulesets: dict[str, RuleSet] = {}
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
        if signal in signals:
            continue
        signals.append(signal)
        if selects_signal_rules(rule_kinds):
            try:
                rulesets[signal] = load_rules(rules_path(signal, rules_dir))
            except ExpansionError as error:
                raise ExpansionError(f"{sidecar_path(path)}: {error}") from None

    by_signal: dict[str, tuple[Rule, ...]] = {}
    for signal in signals:
        ruleset = rulesets.get(signal)
        combined = (ruleset.rules if ruleset is not None else ()) + class_rules
        if not combined:
            raise ExpansionError(
                f"the selection --rules {rule_kinds!r} leaves {signal!r} with no rules at all; "
                "writing an untouched copy of a tree under a name that says 'expanded' is a "
                "silent no-op an arm comparison cannot see"
            )
        by_signal[signal] = combined

    for field_name in TREE_AGREEMENT_FIELDS:
        values = {json.dumps(stats.get(field_name), sort_keys=True) for stats in sidecars}
        if len(values) > 1:
            raise ExpansionError(
                f"the sidecars under --in-dir disagree on {field_name!r} "
                f"({', '.join(sorted(values))}); this tree was half-regenerated, and expanding "
                "it would hide that until training time"
            )

    sources = tuple(rulesets[signal].source for signal in signals if signal in rulesets)
    sources += tuple(class_set.source for class_set in class_sets)
    return TreeRules(
        by_signal=by_signal,
        sources=sources,
        class_groups=tuple(class_set.group for class_set in class_sets),
    )


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
    rules: Sequence[Rule],
    signal: str,
    sources: Sequence[RuleSource],
    class_groups: Sequence[str] = (),
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
            result = expand_example(record["text"], rules, rng, rate=rate)
        record["text"] = result.text
        meta = record.get("meta", {})
        label = label_name(record.get("labels", {}).get(signal))
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
        sources=sources,
        class_groups=class_groups,
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
    classes_dir: Path | None = None,
    rule_kinds: str = "both",
    class_groups: Sequence[str] | None = None,
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
    loaded = check_tree(
        paths,
        sidecars,
        rules_dir=rules_dir,
        classes_dir=classes_dir,
        rule_kinds=rule_kinds,
        class_groups=class_groups,
    )

    known = set(paths) | {sidecar_path(path) for path in paths}
    total = ExpansionTally()
    for path, stats in zip(paths, sidecars, strict=True):
        target = out_dir / path.relative_to(in_dir)
        total.merge(
            expand_file(
                path,
                target,
                rules=loaded.by_signal[stats["signal"]],
                signal=str(stats["signal"]),
                sources=loaded.sources_for(str(stats["signal"])),
                class_groups=loaded.class_groups,
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


# ---------------------------------------------------------------------------
# The dry run against the library lint (DD6 layer 3's supplement)
# ---------------------------------------------------------------------------


#: The manifest the dry run reads. The libraries as committed are the input;
#: nothing here writes.
DEFAULT_MANIFEST = Path("data/synthetic/manifest.json")

#: Name given to the variant in which every rule of a file is applied together,
#: rather than one rule at a time. Not a rule id, and it cannot collide with
#: one: :func:`_check_shape` requires a rule id to be a non-empty string and no
#: author would write this one.
COMBINED = "<all rules together>"


def rewrite_exhaustively(text: str, rules: Sequence[Rule]) -> str:
    """Apply ``rules`` at **every** site they match, with no rate and no draw.

    The worst case, which is what a dry run wants: a rule that is harmless at
    the sampled rate is harmless because of the sampling, not because of the
    rule. Where two rules tie at a site the lowest id wins, so the rewrite is
    deterministic and a reported hit can be reproduced by re-running the mode.
    """
    pieces: list[str] = []
    cursor = 0
    for site in match_sites(text, rules):
        chosen = min(site.rules, key=lambda rule: rule.id)
        pieces.append(text[cursor : site.start])
        pieces.append(_match_leading_case(text[site.start : site.end], chosen.replace))
        cursor = site.end
    pieces.append(text[cursor:])
    return "".join(pieces)


@dataclass(frozen=True)
class HitChange:
    """One lexicon hit that a rewrite introduced, or removed.

    ``variant`` is the rule that did it, or :data:`COMBINED` when the hit only
    appears once the whole file is applied at once -- which is the aggregate
    effect no per-rule load check can see, and the reason this mode exists.
    """

    report: str
    variant: str
    library: str
    signal: str
    fragment_id: str
    before: str
    after: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class DryRunDiff:
    """What a whole dry run found. ``introduced`` is the failure."""

    manifest: Path
    sources: tuple[str, ...]
    rules: int
    fragments: int
    rewritten: int
    introduced: tuple[HitChange, ...]
    removed: tuple[HitChange, ...]

    @property
    def failed(self) -> bool:
        return bool(self.introduced)


def _hit_index(hits: Sequence[LexiconHit]) -> dict[tuple[str, str], LexiconHit]:
    """Index hits by ``(fragment_id, signal)``.

    Existence is the unit, not the term list: :class:`~.lint.CrossSignalCell`
    counts *lines* for the same reason, and a rewrite that changes which term of
    a lexicon matched a line that already matched has not changed what the
    library says about that signal.
    """
    return {(hit.fragment_id, hit.signal): hit for hit in hits}


def _report_hits(fragments: Sequence[Fragment], report: str) -> list[LexiconHit]:
    """Run one of the two reports over ``fragments``.

    ``cross-signal`` is :func:`~.lint.cross_signal_cells` flattened to its hits:
    the cells' rates are computed against a library's full line count and this
    mode only ever holds the changed lines, so a rate here would be a different
    and misleading number. Which cells exist -- every library but a generated
    one, against every signal but its own -- is unchanged.
    """
    if report == "filler":
        return filler_lexicon_hits(fragments)
    return [hit for cell in cross_signal_cells(fragments) for hit in cell.hits]


def _diff_variant(
    originals: Sequence[Fragment],
    rewrites: Sequence[str],
    *,
    variant: str,
) -> tuple[list[HitChange], list[HitChange]]:
    """Diff both reports over one rewrite of the libraries.

    Only the fragments a rewrite actually *changed* are passed to the reports,
    on both sides of the diff. A fragment whose text is byte-identical produces
    byte-identical hits, so restricting the comparison changes no answer and
    turns a whole-manifest lint per rule into one over a handful of lines.
    """
    changed = [
        (fragment, text)
        for fragment, text in zip(originals, rewrites, strict=True)
        if text != fragment.text
    ]
    if not changed:
        return [], []
    before = [fragment for fragment, _ in changed]
    after = [dataclass_replace(fragment, text=text) for fragment, text in changed]
    texts = {fragment.fragment_id: text for fragment, text in changed}

    introduced: list[HitChange] = []
    removed: list[HitChange] = []
    for report in ("filler", "cross-signal"):
        was = _hit_index(_report_hits(before, report))
        now = _hit_index(_report_hits(after, report))
        originals_by_id = {fragment.fragment_id: fragment for fragment in before}
        for key in sorted(set(now) - set(was)):
            hit = now[key]
            introduced.append(
                HitChange(
                    report=report,
                    variant=variant,
                    library=hit.library,
                    signal=hit.signal,
                    fragment_id=hit.fragment_id,
                    before=originals_by_id[hit.fragment_id].text,
                    after=texts[hit.fragment_id],
                    terms=hit.terms,
                )
            )
        for key in sorted(set(was) - set(now)):
            hit = was[key]
            removed.append(
                HitChange(
                    report=report,
                    variant=variant,
                    library=hit.library,
                    signal=hit.signal,
                    fragment_id=hit.fragment_id,
                    before=originals_by_id[hit.fragment_id].text,
                    after=texts[hit.fragment_id],
                    terms=hit.terms,
                )
            )
    return introduced, removed


def dry_run_lint(
    manifest_path: Path,
    sources: Sequence[RuleSource],
) -> DryRunDiff:
    """Apply every rule to every library line and diff the two library reports.

    **This mode reads the libraries and writes nothing.** No tree is generated,
    no tree is expanded, no file is opened for writing; the manifest and the
    rule files are inputs and the report goes to stdout.

    It is the aggregate supplement to DD6 layer 3. The per-rule check at load
    time asks whether a *phrase* changes signal; this asks what happens when the
    rule is let loose on the actual library text, where a rule that is
    individually harmless can still put another signal's language into a library
    declared silent about it -- a lexicon match needing an anchor and a modifier
    can be completed by a swap that carries neither on its own.

    Every rule is applied **unconditionally**, not at ``--rate``, once per rule
    and once with the whole file at play. Two things come back: hits the
    rewrites introduced, which are the failure, and hits they removed, which are
    not a failure but have changed what a library says and want reading.

    ``check_cells=False`` is the lint's own posture, for the lint's own reason:
    a check that refuses to run because the libraries are unbalanced is useless
    exactly when it is most needed.
    """
    try:
        fragments = load_fragments(manifest_path, check_cells=False)
    except ManifestError as error:
        raise ExpansionError(f"{manifest_path}: {error}") from None

    introduced: list[HitChange] = []
    removed: list[HitChange] = []
    rewritten: set[str] = set()
    for source in sources:
        variants: list[tuple[str, tuple[Rule, ...]]] = [(rule.id, (rule,)) for rule in source.rules]
        if len(source.rules) > 1:
            variants.append((COMBINED, source.rules))
        for variant, rules in variants:
            texts = [rewrite_exhaustively(fragment.text, rules) for fragment in fragments]
            rewritten.update(
                fragment.fragment_id
                for fragment, text in zip(fragments, texts, strict=True)
                if text != fragment.text
            )
            new, gone = _diff_variant(fragments, texts, variant=variant)
            introduced.extend(new)
            removed.extend(gone)

    return DryRunDiff(
        manifest=manifest_path,
        sources=tuple(source.label for source in sources),
        rules=sum(len(source.rules) for source in sources),
        fragments=len(fragments),
        rewritten=len(rewritten),
        introduced=tuple(introduced),
        removed=tuple(removed),
    )


def _render_changes(changes: Sequence[HitChange]) -> list[str]:
    lines: list[str] = []
    for change in changes:
        lines.append(
            f"  [{change.report}] rule {change.variant} -> {change.fragment_id} "
            f"({change.library}) reads as {change.signal} ({', '.join(change.terms)})"
        )
        lines.append(f"      before: {change.before}")
        lines.append(f"      after:  {change.after}")
    return lines


def render_dry_run(diff: DryRunDiff) -> list[str]:
    """The report, worst first, with the verdict on the last line."""
    lines = [
        "Rule dry run against the library lint",
        "=====================================",
        f"manifest: {diff.manifest}",
        f"sources:  {', '.join(diff.sources) or 'none'}",
        f"rules:    {diff.rules}, applied unconditionally to {diff.fragments} library lines",
        f"lines any rule rewrites: {diff.rewritten}",
        "",
    ]
    if diff.introduced:
        lines.append(f"INTRODUCED hits ({len(diff.introduced)}) -- these are failures:")
        lines.extend(_render_changes(diff.introduced))
    else:
        lines.append("INTRODUCED hits: none.")
    lines.append("")
    if diff.removed:
        # Not a failure, and not noise either: an existing hit is a labelling
        # decision somebody made, and a rule that makes one disappear has
        # changed what that library says.
        lines.append(f"REMOVED hits ({len(diff.removed)}) -- not failures, but read them:")
        lines.extend(_render_changes(diff.removed))
    else:
        lines.append("REMOVED hits: none.")
    lines.append("")
    lines.append(
        "FAIL: a rule manufactured a lexicon hit the committed libraries do not have."
        if diff.failed
        else "PASS: no rule manufactures a lexicon hit the committed libraries do not have."
    )
    return lines


def load_rulesets(
    signal: str | None,
    rules_dir: Path,
    *,
    classes_dir: Path | None = None,
    rule_kinds: str = "both",
    class_groups: Sequence[str] | None = None,
) -> list[RuleSource]:
    """Every file the dry run should check, as :class:`RuleSource` entries.

    The defaults are what CI runs: every ``*.rules.json`` under ``--rules-dir``
    and every ``*.classes.json`` under ``--classes-dir``. ``--signal`` narrows
    the first, ``--class-groups`` the second, and ``--rules`` drops either
    side entirely.

    An empty ``classes/`` directory is not an error: the dry run lints what is
    committed and writes nothing, so "no class files" is a true answer, and the
    header prints the sources it checked so that the answer is visible rather
    than assumed. A *named* group that is not on disk is still fatal.
    """
    if rule_kinds not in RULE_KINDS:
        raise ExpansionError(f"--rules must be one of {', '.join(RULE_KINDS)}, got {rule_kinds!r}")
    sources: list[RuleSource] = []
    if selects_signal_rules(rule_kinds):
        if signal is not None:
            sources.append(load_rules(rules_path(signal, rules_dir)).source)
        else:
            paths = sorted(rules_dir.glob("*.rules.json"))
            if not paths:
                raise ExpansionError(f"no '*.rules.json' files under {rules_dir}")
            sources.extend(load_rules(path).source for path in paths)
    class_sets = _selected_class_sets(
        rule_kinds, classes_dir=classes_dir, class_groups=class_groups
    )
    sources.extend(class_set.source for class_set in class_sets)
    if not sources:
        raise ExpansionError(
            f"--rules {rule_kinds!r} selected no rule files at all; there is nothing to dry-run"
        )
    return sources


def _rate(raw: str) -> float:
    value = float(raw)
    if not 0 < value <= 1:
        raise argparse.ArgumentTypeError(f"must be in (0, 1]: {raw}")
    return value


def _groups(raw: str) -> tuple[str, ...]:
    """Parse ``--class-groups``. An empty entry is a typo, not an empty group."""
    groups = [part.strip() for part in raw.split(",")]
    if not groups or any(not group for group in groups):
        raise argparse.ArgumentTypeError(f"not a comma-separated list of group names: {raw!r}")
    duplicates = sorted({group for group in groups if groups.count(group) > 1})
    if duplicates:
        raise argparse.ArgumentTypeError(f"repeated group(s): {', '.join(duplicates)}")
    return tuple(groups)


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
    # --in-dir, --out-dir and --rate are required to expand a tree and
    # meaningless to --dry-run-lint, which reads the libraries instead, so
    # requiredness is enforced in main() rather than by argparse -- the same
    # split '__main__.py' makes for --lint.
    parser.add_argument("--in-dir", type=Path, help="a generated fold tree")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="where the expanded copy goes; must be a sibling of --in-dir, never inside it",
    )
    parser.add_argument(
        "--rate",
        type=_rate,
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
        "--classes-dir",
        type=Path,
        default=CLASSES_ROOT,
        help=f"directory holding '<group>.classes.json' (default: {CLASSES_ROOT})",
    )
    parser.add_argument(
        "--rules",
        choices=RULE_KINDS,
        default="both",
        dest="rule_kinds",
        help="which rules an arm applies (DD5). 'signal' is the hand-written "
        "'<signal>.rules.json' alone and reproduces the v1 arm byte for byte; 'classes' is the "
        "swap classes alone, which belong to no signal; 'both' concatenates them and is the "
        "decision arm (default: both)",
    )
    parser.add_argument(
        "--class-groups",
        type=_groups,
        default=None,
        help="comma-separated swap-class groups to load, e.g. 'referent,calendar,setting'. The "
        "default is every group with a file in --classes-dir; a named group with no file is an "
        "error rather than an empty selection",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write into a non-empty --out-dir",
    )
    parser.add_argument(
        "--dry-run-lint",
        action="store_true",
        help="apply every rule to every committed library line unconditionally and diff the "
        "filler-purity and cross-signal reports against the same two over the originals. "
        "Reads the libraries and writes nothing: no tree is generated and none is expanded. "
        "A hit a rule manufactured is a failure; a hit it removed is printed and is not. "
        "With no other flags it covers every rule file and every class file, which is what "
        "CI runs; the cost is linear in rule count, so budget minutes rather than seconds",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"the library manifest --dry-run-lint reads (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--signal",
        help="with --dry-run-lint, check only this signal's rule file; the default checks "
        "every rule file in --rules-dir. It narrows the '*.rules.json' side only -- the class "
        "files belong to no signal, and --class-groups is what narrows those",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.dry_run_lint:
        try:
            diff = dry_run_lint(
                args.manifest,
                load_rulesets(
                    args.signal,
                    args.rules_dir,
                    classes_dir=args.classes_dir,
                    rule_kinds=args.rule_kinds,
                    class_groups=args.class_groups,
                ),
            )
        except ExpansionError as error:
            print(f"error: {error}", file=sys.stderr)
            return 2
        print("\n".join(render_dry_run(diff)))
        return 1 if diff.failed else 0

    missing = [
        name
        for name, value in (
            ("--in-dir", args.in_dir),
            ("--out-dir", args.out_dir),
            ("--rate", args.rate),
        )
        if value is None
    ]
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")
    try:
        tally = expand_tree(
            args.in_dir,
            args.out_dir,
            rate=args.rate,
            seed=args.seed,
            clean_share=args.clean_share,
            rules_dir=args.rules_dir,
            classes_dir=args.classes_dir,
            rule_kinds=args.rule_kinds,
            class_groups=args.class_groups,
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
