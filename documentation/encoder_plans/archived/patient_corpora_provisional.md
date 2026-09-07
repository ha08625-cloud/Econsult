# Abandoned: public patient-written corpora as an idea source (DD2b)

**Status: abandoned on 2026-09-06, before any work was done. It fails the
scalability test that the parent plan exists to satisfy.** This document is the
record of why, so the idea is not re-proposed in six months looking cheap.

Parent: `beyond_augmentation_provisional.md` DD2(b), and DD9 which depended on
the same corpus.

---

## 1. What was proposed

Reading public patient-written corpora "as a source of *ideas and register*
rather than of training text", to feed DD4's idea inventory: the HealthCareMagic
and iCliniq sets distributed with ChatDoctor, MedDialog, the r/AskDocs academic
releases, and — needing no dataset — Patient.info and HealthUnlocked.

## 2. Why it is abandoned

**The reason that decides it, and it decides it on its own.** Every version of
this workstream costs human hours per library, per signal, per condition. The
procedural generation pipeline exists precisely because the project has to reach
165 questions across multiple conditions, and §2.3 puts that at roughly 1,150
libraries. A source of ideas that consumes a person's attention per library does
not reach 1,150 libraries, and no refinement of the reading protocol changes
that. **The workstream is O(hours × signals × conditions) and the constraint it
was meant to relieve is exactly that.**

Substituting a better human does not help. The maintainer is a GP, so the
clinician access this plan's earlier draft treated as the scarce resource is in
fact unrestricted — and it is still the case that no clinician enumerates 40
distinct ideas per library on demand. That is a limit of human enumeration, not
of forums, and `fragment_authoring_prompts.md` §1 records an LLM hitting the
same wall from the other side (forty fragments, six ideas). Swapping one
enumerator for another does not move it.

Three further findings, each of which would have been sufficient on its own:

**The three dataset releases carry no licence to anyone downstream.**
MedDialog's own documentation states copyright in the raw dialogues belongs to
healthcaremagic.com and icliniq.com. ChatDoctor's HealthCareMagic-100k and
iCliniq-10k are the same scraped text with no specified data licence on the
mirrors; the repository's licence covers its code. Reddit's user agreement
grants third parties nothing, so an academic derivative's own open licence does
not reach the underlying corpus. HealthUnlocked's terms permit "non-commercial
individual reference" only. *Not checked, blocked by this environment's egress
proxy: `patient.info`'s terms and the CSIRO MedRedQA licence record.* This is
not legal advice, but the shape does not turn on a fine reading: nobody in the
chain had permission to pass on.

**The "register" half was already refuted by the project's own measurements.**
Register-as-vocabulary is a surface-form change, and §1's table records lexical
variants at −0.21 decisive points and the noise pass at nil on clean text.
Mining a corpus for how patients word things is mining the family §1 says is
exhausted. Only the *ideas* half was ever live.

**The datasets are the wrong dialect and forums are the wrong genre.** All three
releases are US/India-facing; this is a UK NHS product, and for UTI the lay
vocabulary diverges (*water infection*, *cystitis*, *my GP*, *111* against *UTI*,
*my PCP*, *the ER*), which would under-supply exactly the idiom-carried claims
DD8 item 1 wants. Separately, a forum post is written to strangers with no
record, answers no `encoder_prompt`, and carries no request — where an e-consult
is written to the patient's own GP and asks for something. §9 already records
urgency and justification language as a live shortcut in the libraries, so
forums under-supply the one family that is known to be contaminated.

## 3. What is lost by abandoning it, stated rather than glossed

§2.2's problem — the library author, the holdout labeller and the holdout writer
are one person — had no other external check on the *idea space*. Dropping this
does not solve that; it means nothing addresses it. The loss is judged
acceptable because DD2(a)'s multi-writer set attacks §2.2 more directly and
produces labelled text, but it is a loss and not a free deletion.

## 4. DD9 goes with it

Domain-adaptive pretraining needed megabytes of unlabelled in-register text and
there is no licensed source of UK patient free-text at that scale. Combined with
the parent plan's own prediction 3 — that DAPT moves decisive accuracy by less
than 2 points, inside the intervals — **DD9 has a blocked input and a predicted
negligible output. Dropped for cause, not deferred.** T7 disappears and T6 has
the night to itself.

## 5. The test this raises for the rest of the parent plan

The scalability test that killed this workstream was never applied to the others,
and it does not stop here. Recorded for the stage-2 pass to accept or reject;
nothing in `beyond_augmentation_provisional.md` has been edited on the strength
of it.

| item | scales to 165 questions across conditions? | |
|---|---|---|
| **DD3** freeze the margin | **yes** | a one-off change to how comparisons are read |
| **DD11** LLM ceiling reading | **yes, twice over** | cheap to take, and a model that reads the question as input is 165-question-shaped by construction, so a good result is itself a scalability finding |
| **DD10** question-conditioned model | **yes — the only item that changes the exponent** | the marginal cost of question 166 becomes a question string plus a policy decision |
| **DD2(a)** multi-writer dev set | **once, not per condition** | see below |
| **DD4–DD8** the authoring loop | **no** | |
| DD9 DAPT | — | dead, §4 |
| DD2(b) | — | dead, this document |

**DD4–DD8 fail the same test as this workstream and it is less obvious that they
do.** Mining, minimal pairs and a scripted drafting loop make authoring a library
*cheaper*; none of them make it *unnecessary*. 1,150 libraries at even an hour
each is 1,150 hours, and a threefold cost reduction on a process that does not
scale is a process that does not scale. They are worth keeping as the
contingency for DD10 failing — which is what DD12 already says — rather than as
half the plan.

**DD2(a) survives on a distinction worth writing down explicitly.** As a
per-condition evaluation set it fails this test as badly as anything here. As a
*one-off* answer to "is a synthetic number evidence about real text, and does one
person's voice generalise?", it is needed once, for one condition, and the answer
transfers. The version of DD2(a) that quietly becomes 200 submissions per
condition is dead on arrival, and the plan should say which one it means.

**Proposed reordering, for the stage-2 pass: DD3 → DD11 → DD10**, with DD4–DD8
contingent on DD10's leave-one-signal-out result.

## 6. Where the maintainer being a GP is worth spending, since it is not here

Not authoring, for the reason in §2. Two places where clinical judgement is
O(1) per question *class* rather than per library, and therefore does scale:

1. **Labelling policy.** §9's `urinary_frequency_present` and
   `recent_uti_present` rules are the model: written once, load-bearing on
   hundreds of fragments, and they generalise across conditions because "compare
   against the patient's own baseline" is not a UTI fact. **The 101 compound
   questions (OQ6) are an entire unwritten class of exactly this kind**, and they
   are currently an open question rather than a workstream.
2. **`data/realistic/README.md` understates its own evidence.** It records the
   labels as "weaker evidence than one labelled by a clinician who had never seen
   the fragment libraries" and does not mention that the maintainer is a GP. The
   remaining limitation is having seen the libraries, not an absence of clinical
   judgement. That paragraph is quoted into reports and should be corrected.
