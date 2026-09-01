"""Procedural declarative multi-symptom fragments: frames, sampler, renderer.

The hand-written libraries make exactly one claim per line, and the sixty-seven
real submissions say the median patient asserts something about two of the six
signals in one message. Writing the multi-claim lines by hand does not scale --
six signals at two-to-four claims a sentence is several hundred distinct label
combinations -- so this module composes them instead, out of an authored phrase
inventory and two sentence frames.

The label-first invariant (``arch_training.md`` section 2) is strengthened
rather than weakened by that. A generated line's label is never read off its
text: the label is drawn first and the text is *constructed from* it.

**The output is a committed build artefact, not a runtime expansion** (DD1).
``python -m scripts.synthetic_data --build-declarative`` writes a JSONL library
into the tree and that file is reviewed and committed; recombination then reads
it exactly as it reads any other library, and its fragments get ids, cluster
keys and split assignments through the same machinery as everything else. The
point of the round trip through disk is that a human can read the sentences
before they become training text, which is the only thing that catches "I have
not had any getting up in the night" before a model does.

Two properties this module is responsible for, both of them load-bearing:

* **Determinism.** One seeded ``random.Random`` drives every draw, in a fixed
  order, and the output is sorted before writing. ``--build-declarative
  --check`` regenerates into memory and compares, so the committed library and
  the inventory cannot drift apart silently.
* **Label neutrality of the frames** (DD7). Every frame generates every
  polarity: the positive base produces all-true sentences *and* the mixed
  "true, but not false" ones, and the negative base mirrors it. Frame identity
  therefore does not correlate with the label -- a claim the stats sidecar's
  ``declarative.frame_by_label_mode`` re-checks on every run that draws from
  here.

What it deliberately does not do: hard cases. Every line is an unhedged,
canonical, first-person claim, because a fixed frame cannot express a hedge, a
metaphor or a third-party attribution (DD3). The hand-written ``ambiguous`` and
``confounder`` libraries remain the only source of those, and a dataset that
grows in line count here has not grown in difficulty.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .normalise import normalise

#: The authored phrase inventory, and the generated library it composes into.
#: Both live in the library tree rather than beside this module: the inventory
#: is data that a clinician reads and edits, and the output is a library.
DEFAULT_INVENTORY = Path("data/synthetic/conditions/uti/declarative/phrases.json")
DEFAULT_OUT = Path("data/synthetic/conditions/uti/declarative/declarative_v1.jsonl")

#: The budget and mix the committed library was built with, and therefore what
#: ``--check`` regenerates. About two lines per cluster: enough for a cluster to
#: be a real cluster, few enough that the library does not dominate a merged
#: pool even before ``--declarative-share`` is considered (DD15).
DEFAULT_TARGET_COUNT = 1000
DEFAULT_ARITY_WEIGHTS = "2=0.5,3=0.35,4=0.15"

#: Arity 1 is excluded rather than merely unweighted: a one-symptom declarative
#: sentence is what the hand-written libraries already are, and stiffer. The
#: ceiling is the provisional's, and five- and six-symptom sentences are out of
#: scope for v1.
ARITY_FLOOR = 2
ARITY_CEILING = 4

#: Signals the inventory may not carry. ``recent_uti_present`` is not a
#: symptom-presence signal: its label turns on a 30-day window and the six
#: policy rules of ``arch_training.md`` section 9, so "I have had a recent urine
#: infection" is a policy judgement wearing a declarative sentence's clothes and
#: no frame here can place an infection inside the window (DD9).
EXCLUDED_SIGNALS = frozenset({"recent_uti_present"})

#: The one pair of signals whose overlap is undecided. "Up three times in the
#: night for a wee" genuinely asserts both nocturia and urinary frequency, the
#: overlap is a per-line fact, and nobody has decided the general rule -- so the
#: manifest leaves those cells undeclared (section 4) and so does this. A line
#: asserting one of the pair and not mentioning the other emits **no key** for
#: the other, which makes it ineligible for that signal's run rather than
#: wrongly labelled. Deciding the rule is a separate ticket, and its home is the
#: inventory, where it is a handful of phrase-level decisions rather than one
#: blanket one (DD14).
PARTNERED_SIGNALS: Mapping[str, str] = {
    "nocturia_present": "urinary_frequency_present",
    "urinary_frequency_present": "nocturia_present",
}

#: How many consecutive redraws a duplicate may cost before the run gives up.
#: Duplicates are redrawn rather than emitted because ``deduplicate()``
#: downstream would drop them anyway, and the realised count would then not be
#: the count asked for (instruction 5).
REDRAW_LIMIT = 200

#: The longest a bare phrase may be, in words. The mechanical half of "reads
#: correctly after both bases"; the other half is review. The negated form is
#: exempt because it usually carries a prepended "any".
MAX_PHRASE_WORDS = 4


class DeclarativeError(ValueError):
    """Raised when the inventory, the flags, or the generation budget are invalid."""


@dataclass(frozen=True)
class Phrase:
    """One authored noun or gerund phrase, in its two surface forms.

    ``negated`` is authored per phrase rather than derived, because the obvious
    derivation is wrong often enough to ship broken English: "a fever" negates
    to "any fever", not to "any a fever", and "a temperature" negates to itself
    (DD11). The generator uses ``text`` after a positive base and ``negated``
    after "but not" or a negative base.
    """

    text: str
    negated: str


@dataclass(frozen=True)
class Line:
    """One generated fragment: the sentence, its label vector and its cluster."""

    text: str
    #: Sorted by signal. ``True``/``False`` assert, ``None`` declares the line
    #: silent, and a signal *absent* from it is undeclared -- exactly the four
    #: states ``Fragment.value_for`` distinguishes.
    labels: Mapping[str, bool | None]
    cluster: str
    meta: Mapping[str, object]

    def as_record(self) -> dict[str, object]:
        """Return the JSONL object, with keys in the order the format documents."""
        return {
            "text": self.text,
            "labels": dict(self.labels),
            "cluster": self.cluster,
            "meta": dict(self.meta),
        }


def join_items(items: Sequence[str], *, is_positive: bool, oxford: bool) -> str:
    """Join phrases into one list clause.

    The provisional's Phase 2, plus DD12's Oxford comma. One item is itself, two
    are joined by the conjunction alone, and three or more comma-separate all
    but the last. The conjunction is "and" in a positive list and "or" in a
    negative one, because "I have not had A and B" denies the *conjunction*
    rather than each of them.

    ``oxford`` decides only whether a comma precedes the conjunction in a list
    of three or more. It is a per-line coin flip in the sampler: patients are
    inconsistent about it, and emitting one form only would put a punctuation
    habit into every multi-symptom sentence in the dataset. It changes neither
    the label nor the cluster.
    """
    if not items:
        raise DeclarativeError("join_items was given no items; a clause needs at least one")
    conjunction = "and" if is_positive else "or"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} {conjunction} {items[1]}"
    head = ", ".join(items[:-1])
    separator = "," if oxford else ""
    return f"{head}{separator} {conjunction} {items[-1]}"


def render(
    positive: Sequence[str], negative: Sequence[str], *, lead_true: bool, oxford: bool
) -> tuple[str, str]:
    """Render one sentence from its two polarity blocks; return ``(text, frame)``.

    Four frames, two bases. Which base opens the sentence is decided by which
    polarity block *leads*, not by which is larger (instruction 2), and the
    leading block is a fair coin in the sampler -- so both bases get comparable
    mass and neither becomes a cue for the label.

    The blocks arrive already sorted by polarity (DD13), which is why "I have
    had A, but not B, and C" is unreachable: the sort makes it so, rather than a
    rule rejecting it afterwards.
    """
    if not positive and not negative:
        raise DeclarativeError("render was given no phrases in either polarity block")
    positive_clause = join_items(positive, is_positive=True, oxford=oxford) if positive else ""
    negative_clause = join_items(negative, is_positive=False, oxford=oxford) if negative else ""

    if positive and negative:
        if lead_true:
            return f"I have had {positive_clause}, but not {negative_clause}.", "pos_base_mixed"
        return (
            f"I have not had {negative_clause}, but I have had {positive_clause}.",
            "neg_base_mixed",
        )
    if positive:
        return f"I have had {positive_clause}.", "pos_base"
    return f"I have not had {negative_clause}.", "neg_base"


def load_inventory(path: Path) -> dict[str, tuple[Phrase, ...]]:
    """Read and validate the authored phrase inventory.

    The inventory's keys *are* the in-scope signals: everything the generator
    knows about which signals exist comes from here, so extending coverage is an
    edit to one data file rather than to this module. The rules checked are
    DD10's mechanical half -- a signal that is in scope, a non-empty phrase list,
    both surface forms present and non-blank, and the four-word cap on the bare
    form. The grammatical half ("reads correctly after both bases") and the
    policy half ("its label is unambiguous under section 9") are review, and
    ``test_the_declarative_inventory_is_well_formed_and_never_repeats_a_library_line``
    is what stops a phrase reproducing a hand-written library line verbatim.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise DeclarativeError(f"{path} is not a non-empty object keyed by signal")

    inventory: dict[str, tuple[Phrase, ...]] = {}
    for signal in sorted(payload):
        if signal in EXCLUDED_SIGNALS:
            raise DeclarativeError(
                f"{path} carries {signal!r}, which no declarative frame can state: its label "
                "turns on a 30-day window and the section 9 policy rules, not on whether the "
                "sentence mentions it"
            )
        spec = payload[signal]
        if not isinstance(spec, dict) or "phrases" not in spec:
            raise DeclarativeError(f"{path}: {signal!r} has no 'phrases' list")
        phrases: list[Phrase] = []
        for entry in spec["phrases"]:
            if not isinstance(entry, dict) or set(entry) != {"text", "negated"}:
                raise DeclarativeError(
                    f"{path}: {signal!r} has a phrase that is not a "
                    f"{{'text', 'negated'}} object: {entry!r}"
                )
            text, negated = entry["text"], entry["negated"]
            for form in (text, negated):
                if not isinstance(form, str) or not form.strip():
                    raise DeclarativeError(f"{path}: {signal!r} has a blank phrase form: {entry!r}")
            if len(text.split()) > MAX_PHRASE_WORDS:
                raise DeclarativeError(
                    f"{path}: {signal!r} phrase {text!r} is over {MAX_PHRASE_WORDS} words"
                )
            phrases.append(Phrase(text=text, negated=negated))
        if not phrases:
            raise DeclarativeError(f"{path}: {signal!r} declares no phrases")
        inventory[signal] = tuple(phrases)

    if len(inventory) < ARITY_CEILING:
        raise DeclarativeError(
            f"{path} declares {len(inventory)} signals, fewer than the arity ceiling "
            f"{ARITY_CEILING}; a sentence cannot name more distinct symptoms than exist"
        )
    return inventory


def parse_arity_weights(text: str) -> dict[int, float]:
    """Parse ``2=0.5,3=0.35,4=0.15`` into a validated arity mix.

    Bounded on both sides. Below :data:`ARITY_FLOOR` the sentence makes one
    claim, which is what the hand-written libraries already do; above
    :data:`ARITY_CEILING` it is out of scope for v1. A mix that does not sum to
    one would skew the arity stratification undetectably, so it is rejected
    rather than renormalised.
    """
    weights: dict[int, float] = {}
    for term in (part.strip() for part in text.split(",") if part.strip()):
        key, separator, raw_weight = term.partition("=")
        if not separator:
            raise DeclarativeError(f"--arity-weights term {term!r} is not 'arity=weight'")
        try:
            arity = int(key)
        except ValueError:
            raise DeclarativeError(f"arity {key!r} in --arity-weights is not an integer") from None
        try:
            weight = float(raw_weight)
        except ValueError:
            raise DeclarativeError(
                f"weight {raw_weight!r} for arity {arity} in --arity-weights is not a number"
            ) from None
        if not ARITY_FLOOR <= arity <= ARITY_CEILING:
            raise DeclarativeError(
                f"arity {arity} in --arity-weights is outside [{ARITY_FLOOR}, {ARITY_CEILING}]"
            )
        if weight < 0:
            raise DeclarativeError(f"weight for arity {arity} is negative: {weight}")
        if arity in weights:
            raise DeclarativeError(f"arity {arity} appears twice in --arity-weights")
        weights[arity] = weight

    if not weights:
        raise DeclarativeError("--arity-weights is empty, expected e.g. '2=0.5,3=0.35,4=0.15'")
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-9:
        raise DeclarativeError(f"--arity-weights weights sum to {total!r}, not 1.0")
    return dict(sorted(weights.items()))


def allocate(target_count: int, weights: Mapping[int, float]) -> dict[int, int]:
    """Split the budget across arities by weight, largest remainder first.

    Deterministic rather than drawn: the budget is *stratified* by arity (DD15),
    so the realised mix is the declared mix exactly, and a run's arity counts do
    not wobble with the seed. Within an arity the draw is uniform over clusters,
    which the sampler gets for free by drawing the symptom set uniformly and each
    polarity by a fair coin.
    """
    if target_count < 0:
        raise DeclarativeError(f"--target-count must not be negative: {target_count}")
    exact = {arity: target_count * weight for arity, weight in weights.items()}
    counts = {arity: int(value) for arity, value in exact.items()}
    remainder = target_count - sum(counts.values())
    # Sorted by fractional part descending, then by arity, so ties break the
    # same way on every machine.
    order = sorted(exact, key=lambda arity: (-(exact[arity] - counts[arity]), arity))
    for arity in order[:remainder]:
        counts[arity] += 1
    return dict(sorted(counts.items()))


def line_labels(asserted: Mapping[str, bool], signals: Iterable[str]) -> dict[str, bool | None]:
    """Return the per-line label vector for a set of asserted signals.

    Three of the four states appear here and the fourth is expressed by
    omission: an asserted signal takes its polarity, every other in-scope signal
    is ``None`` (the line is silent about it, and that supervises the head
    towards "not mentioned"), and a signal omitted altogether is undeclared and
    earns no key downstream.

    Exactly one thing is omitted: the nocturia / urinary-frequency partner of an
    asserted-but-unpartnered signal (DD14). ``recent_uti_present`` never appears
    because it is never in the inventory (DD9).
    """
    labels: dict[str, bool | None] = {}
    for signal in signals:
        if signal in asserted:
            labels[signal] = asserted[signal]
            continue
        partner = PARTNERED_SIGNALS.get(signal)
        if partner is not None and partner in asserted:
            # The line asserts one of the pair and does not mention this one.
            # Whether that says anything about this one is undecided, so the
            # line says nothing about it.
            continue
        labels[signal] = None
    return dict(sorted(labels.items()))


def cluster_for(asserted: Mapping[str, bool]) -> str:
    """Return the cluster key: the asserted label content, polarity included.

    ``decl:dysuria-fever+haematuria+``. Two lines in one cluster differ only in
    which phrase was chosen for each symptom and which comma style the frame
    used, which makes them near-duplicates by any reading and puts them in the
    same split. Two lines in different clusters make different claims, which is
    the discrimination we want measured rather than leaked.

    Hashing the *frame* instead (12.1's rule for a templated library) would give
    two clusters and a meaningless split, because here a frame's expansions each
    carry a different label rather than sharing one (DD6).
    """
    parts = [
        f"{signal.removesuffix('_present')}{'+' if asserted[signal] else '-'}"
        for signal in sorted(asserted)
    ]
    return "decl:" + "".join(parts)


def draw_line(rng: random.Random, inventory: Mapping[str, tuple[Phrase, ...]], arity: int) -> Line:
    """Draw one line. Every random decision, in a fixed order, from ``rng``.

    The order is the contract: signals, polarities, phrases, leading block,
    Oxford comma. Every draw happens on every call even where the outcome turns
    out not to matter (an all-true sentence still draws a leading block), so that
    adding or reordering a decision is the only thing that can move the output.
    """
    signals = sorted(inventory)
    chosen = rng.sample(signals, arity)
    polarities = [rng.random() < 0.5 for _ in chosen]
    phrases = [rng.choice(inventory[signal]) for signal in chosen]
    lead_true = rng.random() < 0.5
    oxford = rng.random() < 0.5

    # Sorted into blocks (DD13): the sampled order survives within a block, so
    # phrase order still varies, but a true clause can never interleave with a
    # false one.
    positive = [phrase.text for phrase, is_true in zip(phrases, polarities, strict=True) if is_true]
    negative = [
        phrase.negated for phrase, is_true in zip(phrases, polarities, strict=True) if not is_true
    ]
    text, frame = render(positive, negative, lead_true=lead_true, oxford=oxford)

    asserted = dict(zip(chosen, polarities, strict=True))
    return Line(
        text=text,
        labels=line_labels(asserted, signals),
        cluster=cluster_for(asserted),
        meta={"frame": frame, "arity": arity},
    )


def generate_lines(
    inventory: Mapping[str, tuple[Phrase, ...]],
    *,
    target_count: int,
    arity_weights: Mapping[int, float],
    seed: int,
) -> list[Line]:
    """Generate the library: ``target_count`` distinct lines, stratified by arity.

    Sorted by cluster then text before returning, so the committed file is a
    stable diff rather than a re-shuffle on every regeneration, and so a reader
    scrolling it sees each cluster's siblings together.
    """
    rng = random.Random(seed)
    allocation = allocate(target_count, arity_weights)
    for arity in allocation:
        if arity > len(inventory):
            raise DeclarativeError(
                f"arity {arity} exceeds the {len(inventory)} signals the inventory declares"
            )

    seen: set[str] = set()
    lines: list[Line] = []
    for arity, wanted in allocation.items():
        for _ in range(wanted):
            for attempt in range(REDRAW_LIMIT):
                line = draw_line(rng, inventory, arity)
                key = normalise(line.text)
                if key not in seen:
                    seen.add(key)
                    lines.append(line)
                    break
                if attempt == REDRAW_LIMIT - 1:
                    raise DeclarativeError(
                        f"gave up after {REDRAW_LIMIT} redraws looking for an unseen arity-"
                        f"{arity} sentence: the budget of {target_count} is too large for this "
                        "inventory. Lower --target-count, or author more phrases"
                    )
    lines.sort(key=lambda line: (line.cluster, line.text))
    return lines


def render_jsonl(lines: Iterable[Line]) -> str:
    """Render lines as the library file's exact contents.

    ``ensure_ascii=False`` and explicit ``\\n`` for the same reason the
    recombiner pins them: a file that differs by line ending between a
    developer's machine and CI is not reproducible in any useful sense, and
    ``--check`` compares bytes.
    """
    return "".join(json.dumps(line.as_record(), ensure_ascii=False) + "\n" for line in lines)


def summarise(lines: Sequence[Line]) -> list[str]:
    """Return the per-arity and per-cluster tallies, for the build command to print.

    A budget so small that most clusters are empty, and one so large that every
    cluster carries a dozen near-identical siblings, are both visible here
    (DD15).
    """
    clusters: dict[str, int] = {}
    by_arity: dict[object, int] = {}
    for line in lines:
        clusters[line.cluster] = clusters.get(line.cluster, 0) + 1
        arity = line.meta["arity"]
        by_arity[arity] = by_arity.get(arity, 0) + 1

    report = [f"{len(lines)} lines across {len(clusters)} clusters"]
    for arity in sorted(by_arity, key=str):
        report.append(f"  arity {arity}: {by_arity[arity]} lines")
    if clusters:
        sizes = sorted(clusters.values())
        report.append(
            f"  lines per cluster: min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}"
        )
    frames: dict[object, int] = {}
    for line in lines:
        frame = line.meta["frame"]
        frames[frame] = frames.get(frame, 0) + 1
    for frame in sorted(frames, key=str):
        report.append(f"  frame {frame}: {frames[frame]} lines")
    return report


def build(
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
    target_count: int = DEFAULT_TARGET_COUNT,
    arity_weights: str = DEFAULT_ARITY_WEIGHTS,
    seed: int,
) -> tuple[list[Line], str]:
    """Generate the library and its file contents from the committed inventory."""
    inventory = load_inventory(inventory_path)
    lines = generate_lines(
        inventory,
        target_count=target_count,
        arity_weights=parse_arity_weights(arity_weights),
        seed=seed,
    )
    return lines, render_jsonl(lines)
