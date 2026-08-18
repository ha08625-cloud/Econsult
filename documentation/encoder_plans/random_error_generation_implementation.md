# Implementation Plan: Random character-level errors (12.6)

Step-2 output. This is the review-and-correction pass over `arch_training.md`
section 12.6, expanded into tasks that can each be handed to a fresh chat.

Read first: `arch_training.md` sections 2, 5, 7, 8, 9, 10, 12.6, 12.7;
`arch_encoder_training.md` sections 3, 4b, 4c, 5, 10.

**Section 12.6 stays on disk unchanged until task 6.** Where this document
disagrees with it, this document is the one to build from. The disagreements are
listed in "What changed from 12.6" below, because two of them change what the
ticket does and one of them changes what it costs.

---

# Orientation for someone new to this

The encoder reads a patient's free text and answers seven yes/no/not-mentioned
questions. It is trained on synthetic data: a few hundred hand-written sentence
fragments recombined into thousands of examples. The label is chosen *before*
the text is drawn, so a label can never be wrong about its own text
(`arch_training.md` section 2).

The fragments were typed by authors who were concentrating. Real submissions are
typed into a phone at eleven at night. This ticket builds a script that reads a
finished dataset and writes a second one with random single-character damage —
dropped letters, doubled letters, keyboard-neighbour substitutions,
transpositions, missing apostrophes, lost capitals — so we can find out whether
training on damaged text buys any robustness to damaged text.

**The whole risk of this ticket is one sentence.** Every other step in the
pipeline fixes the label before the text exists, so the text cannot make the
label wrong. This step edits text *after* the label is fixed, so for the first
time a mechanical step can make text stop matching its label. `hot` → `not` is
one substitution. Everything below is about making that impossible by
construction rather than rare by arithmetic.

---

# Plan

Build `scripts/synthetic_data/noise.py`: a post-processing pass over a
generated fold tree that writes a second tree with the same ids, the same
clusters, the same filenames and damaged text. Then build the one piece of
training tooling the experiment needs, and run the experiment.

Four things have to be true before a noisy dataset is worth training on:

1. No edit can change what a sentence claims. Enforced by a **frozen lexicon**,
   in both directions: never damage a frozen token, never produce one.
2. The edit rate cannot correlate with the label. Enforced by applying the pass
   blind to the label, and **proved on every run** by a `noise` block in the
   sidecar reporting edits per hundred words by label.
3. The output tree is loadable by the training tooling with no flags changed —
   same filenames, sidecars present, `token_counts` recomputed.
4. The experiment that says whether to use it is part of this ticket, not a
   follow-up. A single post-noise score is uninterpretable.

---

# Scope

**In scope**

* `scripts/synthetic_data/noise.py` — the pass, its operations, its lexicon, its
  CLI.
* Tests in `tests/test_synthetic_noise.py`.
* One cross-tree evaluation flag in `scripts/encoder_training/` (`--test-dir`),
  which is the only training-side change and does not exist today.
* The 2×2 with a rate sweep, and its report.
* Doc updates: `arch_training.md` 12.6 and 12.7, `arch_encoder_training.md`
  section 4.

**Out of scope**

* Real-word errors — autocorrect substitutions, homophones, dropped words. These
  are the errors that actually survive a phone keyboard's spellcheck (12.6, "What
  it is worth") and they are a different generator. This ticket is the cheap
  half of the problem and should be described that way.
* Any change to `recombine.py`, `manifest.py`, `normalise.py` or the fragment
  libraries. The generator stays byte-identical; every dataset generated so far
  stays reproducible.
* Anything under `data/synthetic/` that is not `data/synthetic/generated/`.
* Moving the frozen lexicon into the manifest. That is 12.5 / step 3 of the
  sequencing, and this ticket deliberately ships the hard-coded list plus a
  guard instead of waiting for it.

---

# What changed from 12.6

Five changes. Two of them change what the pass does, one changes what the
experiment costs, one adds a task that 12.7 says is not needed, and one is a
correction to a stale sentence.

### 1. The protected list is split in two, and 12.6's version blocks its own best operations

12.6 says: "Never edit a token that is in the protected list ... The list is
negation, person, tense and modality words plus the signal vocabulary."

Taken literally that rule deletes the operations 12.6 itself calls the ones most
worth having. "im", "ive", "dont", "cant" are *exactly* the person and negation
words. If protected tokens cannot be touched at all, the apostrophe operation
can never fire on the words it exists for, and the pass is left doing letter
damage to filler.

It also excludes the damage the exercise is *for*. "temperature" is signal
vocabulary, so under 12.6's rule the model never sees "temprature" — and
robustness to a misspelt "temperature" is the headline claim being tested.

**The replacement rule.** Two lists and an operation class, not one list:

* **Frozen tokens** — never damaged by a character operation, never produced by
  one. Negation, person, tense and modality words, plus any signal-vocabulary
  word of **five characters or fewer** (`hot`, `warm`, `no`, `not`, `my`, `his`,
  `had`, `was`, `chills`… — see the word list in task 1). Short words are where a
  single edit is proportionally enormous and where the flip risk actually lives.
* **Signal vocabulary of six characters or more** — damageable by at most one
  character operation per word, provided the result is not a frozen token and
  not another signal word. No single-character edit turns "temperature" into a
  negation; the failure mode is degradation towards unreadable, not inversion.
* **Shape-preserving operations are exempt from the frozen rule.** Dropping an
  apostrophe and folding case cannot change which word a token is: "dont" is the
  negation, "Ive" and "ive" are the same claim. These may apply to frozen
  tokens. Character operations may not.

This is a genuine loosening of 12.6's safety argument and it should be read as
one. The conservative variant stays one flag away: `--freeze-signal-vocabulary`
(default `short`, alternative `all`) reproduces 12.6 exactly, and the rate sweep
in task 5 runs one cell at `all` so the choice is measured rather than asserted.

**If in doubt, ship `all` as the default and let the sweep argue it back.** The
recommendation here is `short`, because `all` makes the experiment unable to
measure the thing it is named after, but this is the one design decision in the
ticket that a reasonable person could take the other way.

### 2. Space deletion needs a neighbour rule

12.6 identifies "nofever" as a hazard and then keeps the operation. Correct, but
the constraint has to be written down: **never delete a space adjacent to a
frozen token.** "no fever" and "not had" stay two words; "on the toilet again"
can weld freely. Same rule in both directions — the space before *and* the space
after.

### 3. The 2×2's cost is stated wrongly, and in the expensive direction

12.6: "Twenty training runs, then, not four — five folds × four cells."

Cells are not training runs. A cell is (training tree × test tree), and training
depends only on the training tree. Four cells is **two trained models evaluated
twice each**. Per fold: 2 training runs, 4 evaluations. Five folds: **10
training runs**, not 20.

The 20 comes back the moment a rate sweep is added, and that is where the budget
should go: clean + three rates = four training trees × five folds = 20 training
runs, 40 evaluations. Same bill as 12.6 quotes, buying a sweep rather than
paying twice for the same models. Task 5 is written this way.

### 4. The training tooling does have to grow something

12.7: "Nor does it depend on the training tooling growing anything: `--data-dir`
already points the runs at an arbitrary tree."

`--data-dir` points a run at *one* tree, and `finetune` trains and evaluates
inside it. Nothing in `scripts/encoder_training/` evaluates a model trained on
tree A against tree B's test split, and two of the four cells are exactly that.
Without a cross-tree flag the 2×2 collapses to "train noisy, test noisy" versus
"train clean, test clean", which is the uninterpretable single number 12.6
correctly refuses.

It is a small change — the trees share example ids, fold configuration and
cluster assignment, so a validated test-split swap is the whole of it — but it
is a task (task 4) and it must land before any GPU time is spent.

### 5. The fever-only guard is stale as written

12.6: "Only fever's vocabulary exists today." That was true when it was written.
`lint.SIGNAL_LEXICONS` now carries lexicons for all seven signals.

They are not a drop-in replacement: they are built to *detect* signal language in
filler, so most are `anchors` + `modifiers` pairs that only mean something
together, and none of them carry negation, person or tense words. But they are a
good seed for the signal-vocabulary half of the frozen list, and flattening
anchors and modifiers into one flat word set errs towards **over**-freezing,
which is the safe direction (fewer words get damaged, no label moves).

So the guard stays, but it is keyed on "a frozen lexicon exists and is non-empty
for this signal" rather than hard-coded to `fever_present`, and the seven signals
come nearly free. The migration target in 12.6 is unchanged: step 3 moves this
into the manifest and the guard comes out.

---

# Design decisions

**DD1 — Post-processing over a directory, never a generator flag.** 12.6's four
reasons stand and are not re-argued here. One addition: the pass must be
importable and testable with no manifest, no ruleset and no pools. If
`noise.py` ever imports `recombine.py`, that has gone wrong.

**DD2 — Filenames preserved, whole tree in, whole tree out.**
`dataset.FOLD_FILENAME` is `{signal}.fold{i}.{split}.jsonl` and
`scripts/encoder_training/` finds files by that pattern under `--data-dir`. A
noisy file named `...train.noisy.jsonl` is invisible to it. Every file in the
input directory is copied through with its name intact, sidecar included.

**DD3 — Per-example RNG keyed on the example id, not the line number.** Seed
each example's `random.Random` from `sha256(f"{seed}|{example_id}")`, not
Python's `hash()` (which is salted per process and would make runs
irreproducible across invocations). Consequence, and the reason for it: noising
a 20,000-line file leaves the first 10,000 lines identical to noising the
10,000-line one, matching section 7's reproducibility property.

**DD4 — Rate is per word, Bernoulli, not per example.** Each word is
independently selected for damage with probability `--rate`. Per-example counts
therefore vary naturally, and the only correlation with the label is the length
one section 9 already describes and measures.

**DD5 — A share of examples is left completely clean.** `--clean-share`
(default 0.25). Drawn from the example's own RNG before anything else, so it is
independent of the label and reproducible. Real submissions run from immaculate
to unreadable; a dataset where every example carries the same error density is
its own kind of unrealistic.

**DD6 — Rejection is on the frozen-token test only, which does not know the
label.** Where a word's draw is rejected, the pass **redraws up to three times
and then leaves the word alone**. No looping. The realised rate therefore lands
slightly below the requested one; that gap is telemetry and is printed and
recorded in the sidecar. Rejection rates can vary by word; they cannot vary by
class, because nothing in the test can see the class.

**DD7 — `generator_version` is not bumped and no required sidecar key changes.**
`dataset._check_fold_agreement` requires the three splits of a fold to agree on
`generator_version`, `signal`, `folds`, `fold_index`, `split_salt`. The pass
preserves all five. The marker that a tree is noisy is the **presence of the
`noise` block**; a clean tree has no such key. That is also the guard against
double-noising (task 2).

**DD8 — `token_counts` is recomputed, everything else about the sidecar is
passed through byte-for-byte.** Deleting a space changes a word count and a
sidecar has to describe the file sitting next to it. `fragments`,
`fragment_pool_sizes`, `fragment_counts`, `requested`, `realised` and the fold
configuration all describe the *fragments*, and the fragments were not edited.

**DD9 — The sidecar must prove rate-by-label equality on every run.** The
`noise` block carries edits per hundred words by label, by label mode, the
realised tally by operation, the realised clean share by label, and the
requested-versus-realised rate gap. Equality holds by construction; so does the
fragment-count mix, and that is measured on every run anyway. If error density
ever tracks the label, the model learns "misspelt ⇒ fever" and every number
downstream is worthless, and nothing else in the pipeline would show it.

**DD10 — The cheap operations ship first.** Casing, apostrophes and terminal
punctuation are what a phone keyboard actually produces, they survive
spellcheck, and they cannot produce a different word. They are task 1's first
three operations, not a footnote to the letter-level ones.

---

# Task 1: The noise operations and the frozen lexicon

**A. State of the world.** Nothing exists yet. This task builds the pure
text-to-text half of the pass: the operations, the frozen lexicon, the
per-example RNG, and the per-example damage function. No file I/O, no CLI, no
sidecar. Task 2 wraps this in the directory pass.

**B. Files and deliverables.**

* New: `scripts/synthetic_data/noise.py` — operations, lexicon, `damage_text`.
* New: `tests/test_synthetic_noise.py` — unit tests on fixed strings.
* Read for context, do not modify: `scripts/synthetic_data/lint.py`
  (`FEVER_LEXICON`, `SIGNAL_LEXICONS`, the `Lexicon` dataclass),
  `scripts/synthetic_data/normalise.py`.

**C. Instructions.**

1. **The frozen lexicon.** Build `frozen_tokens(signal: str) -> frozenset[str]`
   from two sources:

   * A module-level `STRUCTURAL_FROZEN` tuple, hand-written, shared by every
     signal. It must cover, at minimum: negation (`no`, `not`, `never`, `none`,
     `nothing`, `without`, `nor`, `nope`, `dont`, `don't`, `didnt`, `didn't`,
     `havent`, `haven't`, `hasnt`, `hasn't`, `isnt`, `isn't`, `wasnt`, `wasn't`,
     `arent`, `aren't`, `cant`, `can't`, `couldnt`, `couldn't`, `wouldnt`,
     `wouldn't`, `wont`, `won't`); person (`i`, `im`, `i'm`, `ive`, `i've`, `my`,
     `me`, `he`, `she`, `they`, `his`, `her`, `their`, `him`, `them`, `son`,
     `daughter`, `wife`, `husband`, `mum`, `mother`, `dad`, `father`, `partner`,
     `nan`, `gran`, `he's`, `hes`, `she's`, `shes`); tense (`had`, `has`, `have`,
     `was`, `were`, `is`, `am`, `are`, `been`, `did`, `does`, `do`, `ago`,
     `last`, `since`, `yesterday`, `today`, `tonight`, `now`, `then`, `before`,
     `after`, `week`, `weeks`, `day`, `days`, `month`, `months`); modality
     (`maybe`, `might`, `may`, `could`, `think`, `thought`, `feel`, `felt`,
     `seems`, `seemed`, `probably`, `possibly`, `bit`, `slightly`, `really`,
     `very`).
   * The signal's own vocabulary, flattened from `lint.SIGNAL_LEXICONS[signal]`
     — `terms + anchors + modifiers`, each multi-word phrase split on
     whitespace, each word lowercased. Under `--freeze-signal-vocabulary=short`
     (the default) only words of five characters or fewer join the frozen set,
     and the rest become the *damageable-signal* set. Under `all`, every signal
     word joins the frozen set and the damageable-signal set is empty.

   Both sets are matched **case-insensitively and apostrophe-insensitively**:
   normalise a token for lookup by lowercasing and stripping surrounding
   punctuation, but keep straight and curly apostrophes distinct only by folding
   curly to straight (reuse the fold table's spirit; do not import `normalise`,
   which strips terminal punctuation and would be wrong here).

2. **Tokenisation.** `split_words(text)` yields `(prefix_punctuation, word,
   suffix_punctuation, index)` over whitespace-separated tokens, so an operation
   edits the word and the punctuation reassembles unchanged. A "word" for the
   rate in DD4 is a token whose stripped form is non-empty.

3. **The operations.** Each is a function `(word, rng) -> str | None`, returning
   `None` when it cannot apply (a word with no apostrophe, a single-character
   word, an already-lowercase word).

   Shape-preserving (allowed on frozen tokens):
   * `drop_apostrophe` — `don't` → `dont`, `I've` → `Ive`.
   * `lowercase` — `I` → `i`, `Monday` → `monday`.

   Character-level (forbidden on frozen tokens):
   * `drop_letter`, `double_letter`, `transpose_adjacent`,
     `keyboard_neighbour` — the last one against a module-level QWERTY
     adjacency map (about thirty lines, letters only, both cases handled by
     lowercasing for lookup and restoring the original case).

   Whole-text, applied once per example rather than per word:
   * `drop_terminal_punctuation` — strip a single trailing `.`, `!` or `?`.
   * `drop_space` — delete one space, **never one adjacent to a frozen token on
     either side** (change 2 above).
   * `lowercase_all` — fold the whole example. This is the operation section 8
     records as having separated a whole library by itself, so it is worth
     having as its own thing rather than as an accumulation of per-word
     lowercasing.

   Operation weights are a module-level default dict, overridable by CLI in
   task 2. Default weights should put roughly half the mass on the
   shape-preserving operations (DD10).

4. **`damage_word(word, rng, frozen, damageable)`.** Draw an operation by
   weight; apply it; **reject** the result if the operation was character-level
   and (the original was frozen, or the result normalises to a frozen token, or
   the result normalises to a damageable-signal word other than the original).
   On rejection redraw, at most three times, then return the word unchanged
   (DD6). Return `(new_word, operation_name | None)`.

5. **`damage_text(text, rng, *, rate, signal, freeze_mode) -> (str, Counter)`.**
   Walk the words, Bernoulli-select at `rate`, damage the selected ones, then
   give the whole-text operations their own draw at the same rate scaled per
   example. Return the text and a counter of realised operations. **At most one
   character operation per word** — do not compose.

6. **Tests.** Fixed input strings, no manifest, no ruleset, no fold tree:
   * `hot` is never produced from `not` and `not` never from `hot`, over ten
     thousand draws at rate 1.0 on "I felt hot" and "no temperature, I checked".
   * No frozen token in the input is ever changed by a character operation, over
     the same volume, checked word-by-word.
   * `drop_apostrophe` and `lowercase` **do** fire on `don't` and `I've` (this
     is change 1 — assert the behaviour 12.6 as literally written would forbid).
   * `drop_space` never welds a frozen token to a neighbour.
   * Under `--freeze-signal-vocabulary=all`, "temperature" is never edited;
     under `short`, it sometimes is, and "hot" never is under either.
   * Same seed and same text gives the same output, twice, in one process and
     across two `random.Random` constructions.
   * QWERTY map is symmetric and every letter has at least two neighbours.

---

# Task 2: The directory pass, the sidecar, and the CLI

**A. State of the world.** Task 1 has landed: `damage_text` works on strings and
is tested. This task makes it a runnable pass over a fold tree, with the sidecar
and the guards. After this task the script is usable; the experiment that says
whether to use it is tasks 4 and 5.

**B. Files and deliverables.**

* Modify: `scripts/synthetic_data/noise.py` — add `noise_file`, `noise_tree`,
  `build_noise_stats`, `build_parser`, `main`, and `if __name__ == "__main__"`
  so `python -m scripts.synthetic_data.noise` runs.
* Modify: `tests/test_synthetic_noise.py`.
* Read for context, do not modify: `scripts/synthetic_data/__main__.py`
  (`write_outputs`, argparse style), `scripts/synthetic_data/recombine.py`
  (`build_stats`, `_length_stats`, `to_record`),
  `scripts/encoder_training/dataset.py` (`FOLD_FILENAME`, `sidecar_path`,
  `REQUIRED_STATS_KEYS`, `_check_fold_agreement`).

**C. Instructions.**

1. **CLI.** `--in-dir`, `--out-dir` (both required), `--rate` (required, float
   in `(0, 1]`), `--seed` (default 42), `--clean-share` (default 0.25),
   `--freeze-signal-vocabulary` (`short` | `all`, default `short`),
   `--operation-weights` (a `name=weight,...` string parsed the way
   `__main__.parse_distribution` parses its own, weights normalised not
   required to sum to one), `--force`.

   Argparse style follows `scripts/synthetic_data/__main__.py`: a
   `build_parser()`, a `main(argv=None) -> int`, errors as `SystemExit` with a
   message rather than tracebacks.

2. **Guards, all of them startup errors rather than warnings.**
   * `--out-dir` must not be `--in-dir`, and must not be a parent or child of it.
   * Neither may resolve outside `data/synthetic/generated/`. The script never
     touches `data/synthetic/`.
   * A non-empty `--out-dir` is refused unless `--force`.
   * Every `*.jsonl` in `--in-dir` must have a sidecar beside it
     (`dataset.sidecar_path`), because `dataset._read_stats` refuses to load a
     dataset with no sidecar and emitting the JSONL alone produces a tree that
     fails at training time rather than at noising time.
   * Every sidecar's `signal` must have a non-empty frozen lexicon (change 5). A
     signal with no lexicon is a **silent** failure — the pass runs, the output
     looks fine, and the label noise is invisible in exactly the way section 2
     exists to prevent.
   * Any input sidecar already carrying a `noise` block is refused: noising a
     noisy tree compounds damage in a way no rate describes.
   * All sidecars in the tree must agree on `signal`, `folds` and `split_salt`.
     A half-regenerated input tree should fail here, not at training time.

3. **`noise_file`.** Read the JSONL with `json.loads` per line; for each record
   build `random.Random(int.from_bytes(sha256(f"{seed}|{example_id}").digest()))`
   (DD3); draw the clean-share coin first (DD5); damage `text`; leave
   `example_id`, `split`, `labels` and `meta` **untouched**; write with
   `json.dumps(..., ensure_ascii=False)` and `newline="\n"`, matching
   `write_outputs`. Key order in the record must match `to_record`'s so a diff
   between clean and noisy trees shows only text.

4. **The sidecar.** Deep-copy the input stats; recompute `token_counts` from the
   damaged texts using the same `_length_stats` shape (import it from
   `recombine` — this is the one import from the generator that is justified,
   because two implementations of the same statistic drifting apart is worse
   than the coupling; if that is unwelcome, move `_length_stats` and
   `_percentile` into a small shared module rather than copying them); add:

   ```
   "noise": {
     "source_dir": "<in-dir>",
     "seed": 42,
     "requested": {"rate": 0.02, "clean_share": 0.25,
                   "freeze_signal_vocabulary": "short",
                   "operation_weights": {...}},
     "realised": {
       "edits_per_hundred_words": {"by_label": {...}, "by_label_mode": {...},
                                   "overall": 1.87},
       "clean_share": {"by_label": {...}, "overall": 0.249},
       "operations": {"drop_apostrophe": 412, ...},
       "words": {"total": 98234, "selected": 1964, "edited": 1837,
                 "rejected_then_left_alone": 127}
     }
   }
   ```

   The `by_label` row is the point of the block (DD9). Print the same three
   numbers to stdout at the end of a run: overall realised rate, the largest
   by-label gap, and the rejection count.

5. **Tests.**
   * A two-file tmp tree in, a two-file tree out: filenames identical, sidecars
     present, `example_id`/`labels`/`meta` byte-identical, `text` different for
     roughly `1 - clean_share` of examples.
   * The output tree loads through `dataset.load_fold` with no error (build a
     three-split tmp fold for this; it is the check that the whole integration
     works and it is worth the fixture).
   * Running twice writes byte-identical files.
   * Prefix stability: noise a 200-line file and its first 100 lines; the first
     100 output lines match (DD3).
   * **The rate-by-label test.** Generate a tmp dataset of ~2,000 examples whose
     `true`, `false` and `null` texts are drawn from the same word pool, noise
     it, and assert the realised `edits_per_hundred_words` differ by less than
     10% relative across labels. This is the test that would catch a future
     change making rejection label-aware.
   * Each guard in step 2 raises, with its own test and a message naming the
     path.

---

# Task 3: The lint check (optional, do it if task 2 came in cheap)

**A. State of the world.** The pass runs and writes trees. This task adds the
one check that would catch the pass going wrong on the real libraries rather
than on fixtures.

**B. Files.** Modify `scripts/synthetic_data/lint.py` and its report renderer;
modify `tests/test_synthetic_recombination.py` (the lint tests live there).

**C. Instructions.** Add a report section that, for every signal, lists the
frozen-lexicon words that appear in that signal's *decisive* libraries and the
count of fragments containing them. The number to read is what share of each
library's decisive language is frozen: a library whose every positive fragment
is 90% frozen words will barely be damaged at all, which is a finding about what
the sweep in task 5 can possibly show, not a bug. Print it, do not fail on it.

Skip this task without regret if time is short. It is diagnostics, not a guard.

---

# Task 4: Cross-tree evaluation (`--test-dir`)

**A. State of the world.** The noise pass is done. This is the only training-side
change, and 12.7 is wrong to say none is needed (change 4). It must land before
any GPU time is spent, because two of the four cells cannot be run without it.

**B. Files and deliverables.**

* Modify: `scripts/encoder_training/dataset.py` — add `swap_test_split`.
* Modify: `scripts/encoder_training/__main__.py` — add `--test-dir` to the
  `finetune` subcommand, and record it in the artefact's config block.
* Modify: `scripts/encoder_training/report.py` — the report header must say
  which tree the test split came from when it is not the training tree.
* Modify: `tests/test_encoder_training_dataset.py` and
  `tests/test_encoder_training_arm_b.py`.

**C. Instructions.**

1. `swap_test_split(fold: Fold, test_fold: Fold) -> Fold` returns
   `Fold(train=fold.train, val=fold.val, test=test_fold.test)` after asserting:
   the two folds agree on `signal`, `folds`, `fold_index` and `split_salt`; the
   two test splits have **identical example id sets** and **identical fragment
   id sets**. The id check is what makes the swap meaningful — it is the same
   held-out clusters, differing only in surface form — and it is what stops
   someone pointing `--test-dir` at an unrelated tree and getting a number.
2. `--test-dir` defaults to `None`, meaning today's behaviour exactly. When set,
   `load_folds` runs twice and every fold is passed through `swap_test_split`.
   Do not add it to `probe`, `compare-models` or `joint-compare` — the 2×2 needs
   it on the Arm B fine-tune path and nowhere else, and an unused flag on four
   subcommands is four things to keep correct.
3. The report header prints the test tree's path and its `noise` block's
   requested rate when present, because "which test set is this" is the first
   question anyone reading the 2×2 will ask.
4. Tests: the swap works on two tmp trees with the same ids; it raises when the
   id sets differ, when the fold configs differ, and when `--test-dir` names a
   tree missing a fold.

---

# Task 5: The 2×2 and the rate sweep (GPU — deferred until back from holiday)

**A. State of the world.** Tasks 1, 2 and 4 have landed and are tested. Nothing
here can run without a GPU, so this task is written to be picked up cold. It is
in scope for this ticket, not a follow-up: shipping the script without the
experiment produces a knob nobody can decide whether to turn.

**B. Deliverables.** Four noisy trees, twenty fine-tune runs, one report at
`reports/encoder_training/<date>-noise-2x2.md`, and a paragraph in
`arch_encoder_training.md` section 4.

**C. Instructions.**

1. **Generate the trees.** One clean fold tree (five folds, fold mode, not the
   default bands — per-sub-class numbers on band splits are the 2-to-6-cluster
   slices section 10 says cannot separate two models). Then, from that one tree:

   ```
   for r in 0.01 0.02 0.05; do
     python -m scripts.synthetic_data.noise \
       --in-dir  data/synthetic/generated/folds \
       --out-dir data/synthetic/generated/folds-noisy-r${r#0.} \
       --rate $r --seed 42
   done
   ```

   All four trees rest on the same fragments, the same clusters and the same
   fold assignment. Noise creates no new clusters, so effective n is identical
   across every cell — the only thing that varies is surface form. That is
   unusually clean as experiments here go, and it caps what a win can mean: a
   gain is robustness to damaged surface, never better coverage of the clinical
   space.

2. **Run the cells.** Per fold: train on clean, train on each noisy rate. Then
   evaluate each trained model against both the clean test split and its own
   rate's noisy test split, via `--test-dir`. Twenty training runs, forty
   evaluations. Pin `--train-seed` and use the same seed for every cell.

3. **Optionally add a fifth training tree** at `--rate 0.02
   --freeze-signal-vocabulary all`, which is 12.6's literal rule, to measure
   change 1 rather than assert it. Five more training runs; worth it if the
   headline result at `short` is positive, skippable if it is flat.

4. **Read it as four comparisons, not one number:**
   * noisy-trained vs clean-trained on the **noisy** test set — does training on
     damaged text buy robustness to damaged text? This is the claim.
   * noisy-trained vs clean-trained on the **clean** test set — does it cost
     anything on text that is fine?
   * across rates — "a little noise helps and more does not" and "noise helps"
     are different findings and one rate cannot distinguish them.
   * clean-trained on clean vs clean-trained on noisy — how much damage the
     current model is actually losing to. This is the cell that says whether any
     of this was worth doing, and it needs no noisy training run at all. **Run
     this one first.** If the clean-trained model barely drops on noisy text,
     stop: there is nothing here to buy.

5. **Two reasons the honest outcome may be "no measurable benefit",** and both
   should be in the report's opening paragraph rather than its conclusion. A
   subword tokenizer shatters a misspelt word into pieces carrying little of the
   original meaning, so above some rate this is training on noise rather than on
   harder text; finding that rate is what the sweep is for. And the free-text box
   in `frontend/src/screens/EditScreen.tsx` is a plain `<textarea>` with browser
   spellcheck on, on a phone with autocorrect on top — a large share of the
   nonword typos this pass generates would never reach us. The errors that
   survive that filter are disproportionately real-word errors, which are a
   different generator and probably the more valuable one.

---

# Task 6: Documentation

**A. State of the world.** Everything else has landed. `arch_training.md` 12.6
is still the provisional sketch and now disagrees with the code in five places.

**B. Files.** `documentation/arch_training.md` (12.6, 12.7),
`documentation/arch_encoder_training.md` (section 4),
`documentation/file_structure.md`.

**C. Instructions.** Rewrite 12.6 from "provisional" to "landed", carrying the
five changes above into it — in particular the split frozen lexicon, the
shape-preserving exemption, and the corrected run arithmetic. Strike the
sentence in 12.7 claiming the training tooling needs nothing. Keep the migration
note: the hard-coded lexicon and the signal guard both come out at step 3, when
the lexicon moves into the manifest, and two lists in two modules drifting apart
is the outcome to avoid.

Update the "What it is worth" framing rather than deleting it. Sixty-six
training fragments damaged four ways is still sixty-six ideas; the noisy dataset
carries the same `fragments` provenance block with the same cluster keys, and
the honest count still comes from there.

---

# Testing note

Per `CLAUDE.md`: in-chat, typecheck and run only the touched test files. Do not
run the full suite and do not run `npm run build`. CI's unit job is the gate.

Tasks 1–4 are all CPU and all cheap. Task 5 is the only one needing hardware.
