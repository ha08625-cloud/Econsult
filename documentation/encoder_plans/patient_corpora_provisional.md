# Provisional plan: public patient-written corpora (DD2b of the beyond-augmentation plan)

Splitting `beyond_augmentation_provisional.md` DD2(b) into its own workstream.

Read first: `beyond_augmentation_provisional.md` §1 (the four measured changes),
DD2, DD4, DD8, DD9; `arch_training.md` §9; `data/realistic/README.md`;
`fragment_authoring_prompts.md` §1–2.

---

## 1. What DD2(b) proposed, and what this pass concludes

DD2(b) proposed reading public patient-written corpora "as a source of *ideas
and register* rather than of training text", naming HealthCareMagic and iCliniq
(via ChatDoctor), MedDialog, the r/AskDocs academic releases, and — with no
dataset needed — Patient.info and HealthUnlocked.

Four conclusions, in the order they change the shape of the work.

**1. The "register" half of the proposal is already refuted by the project's own
measurements, and should be dropped.** §1's table records that lexical variants
moved decisive accuracy by −0.21 points and that the noise pass did nothing on
clean text. Both are surface-form changes; register-as-vocabulary *is* a
surface-form change. Mining a corpus for how patients word things is therefore
mining the one family §1 says is exhausted. What survives is the **ideas** half:
distinct *situations* a library does not contain, which is the structural axis
that companions moved 44.5 points on. **This workstream is idea mining. It is
not a register workstream.**

**2. The three dataset releases are unusable, and not marginally.** §2 below.
This is not a "licence review is needed" finding; it is a finding. It removes
DD9's corpus and it removes any machine-readable path into DD4's clustering
step.

**3. The plan lists the sources in the wrong order for a UK product.** All three
datasets are US/India-facing; the two forums it lists last are the two UK
sources. §3.

**4. DD4 does not depend on this workstream and should stop being written as
though it does.** The coverage metric DD4 proposes runs against text the project
already owns and is already allowed to touch. §5.

---

## 2. The licence position, as checked on 2026-09-06

**Caveat before any of it: I am not a lawyer, this is not advice, and two of the
five sources could not be fetched from this environment** (`patient.info` and
`data.csiro.au` are blocked by the egress proxy). Treat the rows marked *unread*
as unchecked rather than as cleared.

| source | licence position found | verdict for a commercial product |
|---|---|---|
| **MedDialog (EN)** | The dataset's own documentation states the raw dialogues are crawled from healthcaremagic.com and icliniq.com and that **all copyright in the data belongs to those two sites**. No licence is granted to anyone downstream. | **No.** There is nothing to gate; no grant exists. |
| **ChatDoctor — HealthCareMagic-100k, iCliniq-10k** | Same upstream text, same upstream copyright. The ChatDoctor repository's own licence covers its *code*; the HuggingFace mirrors carry **no specified data licence**. | **No.** "Licence unspecified" on scraped third-party content is not permission. |
| **r/AskDocs academic releases** (e.g. MedRedQA) | Reddit users license their posts to *Reddit*; Reddit's user agreement grants nothing to third parties, and its post-2023 API terms restrict redistribution. Academic derivatives attach their own terms, typically research-only. *unread* | **Probably no**, and a paper being CC BY does not make its underlying scraped corpus CC BY. Worth one read of the CSIRO DAP licence only if §6 says the workstream is worth continuing at all. |
| **HealthUnlocked** | Terms state site contents are owned or controlled by HealthUnlocked, are **for personal use only**, and may not be copied, downloaded, distributed or republished "other than for non-commercial individual reference". | **Reading in a browser: yes. Any copy, any ingestion, any paste into a model: no.** |
| **Patient.info** | *unread* — blocked. Expect materially the same posture. | Assume the HealthUnlocked position until read. |

### 2.1 What this kills

* **DD9 (domain-adaptive pretraining) loses its corpus.** DAPT needs megabytes of
  unlabelled in-register text and there is no licensed source of UK patient
  free-text at that scale. Combined with the plan's own prediction 3 — that DAPT
  moves decisive accuracy by less than 2 points and lands inside the intervals —
  **DD9 now has a blocked input and a predicted-negligible output. Recommend
  dropping it from the plan rather than carrying it as a gated item.** T7
  disappears; T6 gets the night to itself.
* **DD4's step 2 ("cluster them") loses its external input.** Clustering is
  machine ingestion, which is a copy. The step survives only over text the
  project owns (§5).

### 2.2 The distinction that does survive, stated precisely

Copyright protects **expression, not ideas or facts**. A person reading forum
threads in a browser and writing down *"several patients describe the pain by
comparing it to something physical — glass, razor blades, acid"* has recorded an
idea, not copied a work. That is a genuinely different act from the three things
that break it, and the difference is worth writing down because all three are
easy to drift into:

1. **Pasting post text into an LLM.** That is a copy *and* a transfer to a third
   party *and* almost certainly a terms breach. The authoring loop in DD7 makes
   this the single most likely way the rule gets broken by accident.
2. **Saving posts to a file.** A corpus file under `data/` is a copy, whatever
   it is used for afterwards.
3. **A distinctive phrasing surviving verbatim into a fragment.** An idea is
   free; a memorable sentence is not. This is the only one of the three that
   would end up committed to the repository without anyone noticing.

**Proposed rule (DD-C1), to be added to `fragment_authoring_prompts.md` §2 if
this workstream proceeds:** external reading may leave the browser only as an
*idea line* — a description of a situation in the reader's own words, never a
sentence, never a quotation, never a screenshot, never a paste into a model. No
external text is saved to the repository in any form.

---

## 3. The dialect problem, which is larger than the plan's "register transfers
imperfectly"

DD2(b) records that forum writers are self-selected, longer, often chronic, and
writing to strangers. All true. Two sharper problems sit underneath it.

**3.1 The three datasets are the wrong dialect.** This is a UK NHS product.
HealthCareMagic, iCliniq and r/AskDocs are US- and India-facing. For UTI
specifically the lay vocabulary diverges hard: UK patients write *water
infection*, *cystitis*, *weeing*, *my GP*, *111*, *out of hours*; the US corpora
supply *UTI*, *peeing*, *my PCP*, *the ER*, *urgent care*. An idea inventory
mined from them would systematically under-supply exactly what DD8 item 1 says
the budget should go on — the claim carried by idiom rather than by the
symptom's noun. **The two sources DD2(b) lists last are the only two in the
right dialect, and they are also the two that need no dataset.** The ordering in
DD2(b) should be reversed.

**3.2 A forum post is a different genre from an e-consult, in four ways that
each bias the inventory.**

| | forum post | e-consult submission |
|---|---|---|
| audience | strangers, no record | the patient's own GP, who has their record |
| purpose | "what is this?" | "please do something about this" |
| prompt | none — free-standing | a reply to a specific `encoder_prompt` |
| selection | self-selected for strange, chronic, unresolved | routine, mostly ordinary |

The fourth row is the one that matters most and the third is the one that is
easiest to forget. But the second row carries a live hazard: e-consults contain
a *request* ("can I have some antibiotics", "I need a sick note") and forum
posts largely do not. §9 already records that urgency and justification language
is a live shortcut in the libraries — 17% of `fever_true` against 8% of
`fever_false`. So forums under-supply the request family, and **mining forums to
fix the request family would be the wrong tool applied to the one family the
project already knows is contaminated.**

**Net: forums are a source of *symptom-description* ideas and of nothing else.**
That is a real but narrow contribution, and it is worth scoping the workstream
to it explicitly rather than discovering it halfway through.

---

## 4. What this workstream is actually competing against

DD2(b) is not competing with DD2(a). It is competing with three cheaper things,
and it loses to at least one of them.

| source of ideas | licensed? | in dialect? | e-consult genre? | labelled? | cost |
|---|---|---|---|---|---|
| **a GP who reads e-consults** | yes | yes | **yes** | n/a | an hour of someone's time |
| DD2(a) scenario-card writers, debriefed | yes | yes | yes | yes | already planned |
| the 67 holdout submissions | yes | yes | yes | yes | free, already here |
| UK forum reading (this workstream) | reading only | yes | **no** | no | hours, unbounded |
| the three US datasets | **no** | no | no | no | — |

**The first row is the finding.** DD2(b) never names it, and a GP who has read
thousands of real e-consults is a strictly better idea source than a forum on
every axis: in dialect, in genre, licensed, and able to say which situations are
*common* rather than merely *possible* — which is the thing no amount of forum
reading tells you, because forums are selected for the uncommon.

**The third row is the cheapest and is available today.** The 67 holdout
submissions are in-house, in-genre and already labelled. Reading them for ideas
is not a breach of README rule 2 in spirit *or* in letter — rule 2 forbids using
them to *select* between candidates, and deriving an authoring queue from them
is selection of fragments, which rule 2 names explicitly ("not which fragments
to write next"). **So they are barred.** Recorded here because it is the obvious
move and it is wrong; the plan's own DD1 dev set is what unblocks it, which is
one more reason DD1 comes first.

---

## 5. Cutting DD4's dependency on this workstream

DD4's coverage metric — nearest-synthetic-neighbour distance per real text —
is written in the parent plan as though it needs DD2(a)'s messages and DD2(b)'s
forum reading. It needs neither to be *built*. What it needs is a set of real
texts the rules permit selecting against, which is DD1's `dev` role. The metric
itself is an embedding pass and a distance computation over text the project
already has, and it can be written, tested and demonstrated against the
synthetic libraries alone before any real text exists.

**Proposed: DD4's tooling is unblocked now and depends on DD1, not on DD2(b).**
Forum reading, if it happens, contributes idea lines to the queue the metric
produces; it is not on the critical path to producing the metric.

---

## 6. Design decisions proposed

**DD-C1 — Idea lines only.** As §2.2. External text leaves the browser only as a
situation described in the reader's own words. Nothing saved, nothing pasted
into a model, nothing quoted.

**DD-C2 — Drop the three dataset releases.** MedDialog, ChatDoctor's two sets
and the r/AskDocs derivatives are removed from the plan rather than gated. The
copyright position is not ambiguous enough to be worth a review, and the dialect
is wrong even if it were.

**DD-C3 — Drop DD9 (domain-adaptive pretraining) with it.** No licensed corpus
exists at the scale DAPT needs, and the plan's own prediction 3 puts the effect
inside the intervals. Recorded as dropped-for-cause, not deferred.

**DD-C4 — Reverse the source ordering: UK forums first and only.**
Patient.info and HealthUnlocked, read in a browser, scoped to
symptom-description ideas per §3.2.

**DD-C5 — Ask a GP before reading a forum.** One structured hour with a
clinician who reads e-consults produces a better idea inventory than a day of
forum reading, and it is the only source that reports *frequency* as well as
existence. Forum reading becomes the fallback and the top-up, not the method.

**DD-C6 — The deliverable is an idea inventory file per signal, with
provenance.** `documentation/encoder_plans/idea_inventory_<signal>.md`: one line
per distinct situation, a provenance column (`gp` / `forum` / `scenario-writer`
/ `clinical-knowledge`), and nothing else. Provenance is recorded because
`fragment_authoring_prompts.md` §1 already proposes comparing how well
LLM-drafted clusters are learned against hand-written ones, and the same
comparison is worth having for mined ideas against invented ones. **No source
text appears in the file** — that is DD-C1 restated where the temptation is.

**DD-C7 — A time box, and a stopping rule that is not a feeling.** Forum reading
is unbounded by nature. Proposed: two hours per signal, or until twenty
consecutive posts produce no new idea line, whichever comes first. The second
condition is the useful one and it is the same saturation logic DD4's coverage
metric formalises.

---

## 7. Predictions, recorded before the work

1. **Forum reading yields fewer than 15 genuinely new idea lines per signal** —
   ideas absent from the existing 49 libraries — and most of them land on
   `dysuria` and `flank_pain` rather than on the two worst libraries
   (`urinary_frequency_true`, `nocturia_true`), because those two are worst for
   a boundary reason (DD5) and not for an idea-count reason.
2. **A GP hour beats two hours of forum reading on new-idea count**, and beats
   it by more on *useful* new ideas, because it supplies frequency.
3. **At least one distinctive forum phrasing will try to survive into a draft
   fragment** during DD7's scripted authoring, and DD-C1 will only catch it if
   the rule is in `fragment_authoring_prompts.md` rather than in this file.
4. **The workstream produces no measurable accuracy change on its own.** It is
   an input to DD4/DD5/DD7 and its effect is only visible through them. Anyone
   expecting a number from this workstream directly is measuring the wrong
   thing.

---

## 8. Tasks

* **TC1 — Amend the parent plan.** Fold DD-C2 and DD-C3 into
  `beyond_augmentation_provisional.md`: strike the three dataset releases, strike
  DD9 and T7, reverse DD2(b)'s source ordering, and cut DD4's stated dependency
  on DD2(b) (§5). No code.
* **TC2 — Add DD-C1 to `fragment_authoring_prompts.md` §2**, next to the
  existing house rules, because that is the file an author actually reads.
* **TC3 — The GP hour (DD-C5).** Scheduling and a question sheet. Not a coding
  task and the largest-value item here.
* **TC4 — The idea-inventory file format (DD-C6)** for one signal as a worked
  example. Choose the signal after TC3.
* **TC5 — Forum reading (DD-C4, DD-C7)**, time-boxed, only after TC3 has shown
  what is still missing.
* **TC6 — Read the two blocked licences** (`patient.info` terms; the CSIRO DAP
  MedRedQA licence) from a normal browser, and correct §2 if either differs from
  what is assumed here.

**Nothing in TC1–TC6 needs a GPU, and nothing needs new tooling.**

---

## 9. Open questions

1. **Is a GP or e-consult-reading clinician available for an hour?** DD-C5 turns
   on this, and it changes the ordering of everything below it.
2. **Is the product commercial in the sense the licences mean?** It is being
   deployed to GP practices, so this pass assumes yes. If it were genuinely
   non-commercial research the r/AskDocs derivatives reopen — and the dialect
   objection in §3.1 still stands, so this changes less than it sounds like.
3. **Does §4's reading of README rule 2 hold?** This pass reads "not which
   fragments to write next" as barring the holdout from idea mining. That is the
   conservative reading and it costs the cheapest source on the table. If the
   maintainer reads it otherwise, say so explicitly in the README rather than in
   a plan.
4. **Is DD-C3 (dropping DD9) accepted?** It is the largest deletion this pass
   proposes and it deletes a workstream on a licence finding plus the parent
   plan's own negative prediction, not on a measurement.
5. **Who does TC6, and does it happen at all** if the answer to Q1 is yes and
   the GP hour supplies enough?
