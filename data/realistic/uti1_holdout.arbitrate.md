# Rows to arbitrate first

These are the cells where the call is genuinely arguable rather than a plain
reading of the text. Everything not listed here is unambiguous. Change the value
in `uti1_holdout.labels.tsv` if you disagree -- these are proposed labels, and
the proposal is the part that needs checking.

Two of the recurring judgements are worth settling once rather than row by row:

* **Blood seen on paper when wiping, not in the urine or the bowl.** Rows 11, 39
  and 50. In a GP setting that distinction matters -- it can be gynaecological
  rather than urinary -- and the ruleset asks whether the patient has *noticed
  blood in their urine*. I have called bowl/urine sightings `true` and
  paper-only sightings `null`, except row 39 where the context is waking to pee.
  If you would rather paper-only count as `true`, three cells change.
* **Downplayed pain: "doesn't hurt too badly", "doesn't hurt terribly yet".**
  Rows 54, 60, 62. These admit some discomfort while minimising it. I have
  called the two that lead with a denial `null` and the one that names a
  specific end-of-stream discomfort `true`. A stricter reading would make 54 and
  60 `false`.

### holdout-0004 — `recent_uti_present` = `false`

> I would like to have a course if atrong antibiotics. Last year i was hospitalised with a severe kidney infection and ended up on a drip with a raging fever and im pretty sure ive got a fever now, and im peeing every ten minutes

kidney infection 'last year' -- outside 30 days, so false rather than null.

### holdout-0011 — `haematuria_present` = `null`

> I woke up this morning with SEVERE lower stomach cramping and an urgent need to urinate. There was a bit of pinkish blood on the toilet paper when I wiped. I feel completely exhausted and need to know if I can get antibiotics.

'pinkish blood on the toilet paper when I wiped' -- on wiping, not seen in urine; could be vaginal. Called null.

### holdout-0018 — `nocturia_present` = `null`

> Woke up in the night with sharp cramping in my lower abdomen and intense burning when passing water. Urine was pink-tinted. It's so painful I was brought to tears this morning.

woke in the night with cramping, not stated as waking *to pass urine*. Called null.

### holdout-0021 — `fever_present` = `true`

> Extremely painful urinating, feeling hot and cold, and a constant throbbing pain in my right flank and lower back. I feel nauseous and completely wiped out. I cannot cope with this.Started as a mild sting two days ago and rapidly worsened today.

'feeling hot and cold' -- chills without the word fever. Called true.

### holdout-0022 — `dysuria_present` = `true`

> My urine is very cloudy and has dark specks in it today. Burning sensation is moderate, but the pressure in my lower pelvis makes it painful to sit down at my desk for long periods. I cant carry on working like this

'Burning sensation is moderate' -- never says on passing urine, inferred from context. Called true.

### holdout-0034 — `fever_present` = `null`

> Mild stinging when urinating that started two days ago. I also feel a bit bloated and heavy in my lower abdomen, but otherwise feel fine in myself.

'otherwise feel fine in myself' -- too vague to be a fever denial. Called null, not false.

### holdout-0039 — `haematuria_present` = `true`

> I wake up every 45 minutes to pee, and it stings like razor blades. There was a little bit of blood on the tissue. I have a big exam tomorrow and I can't concentrate at all.

'blood on the tissue' after waking to pee -- called true, but same wiping ambiguity as 11.

### holdout-0050 — `haematuria_present` = `null`

> I noticed some light pink spotting on the toilet paper this morning and the burning sensation has gotten much worse since yesterday. I started taking over-the-counter cystitis sachet drinks yesterday afternoon, but they don't seem to be helping at all with the urgency.

'light pink spotting on the toilet paper' -- 'spotting' leans gynaecological. Called null.

### holdout-0054 — `dysuria_present` = `null`

> My urine has been very dark and cloudy for three days now, and there's a strong, unpleasant odor. It doesn't hurt too badly to pee, but I am having to get up four or five times a night, which is completely disrupting my sleep. Ive had some antibiotics prescribed to me already, so i just need a note for my travel insurance to say i cant fly

'It doesn't hurt too badly to pee' -- admits some pain while downplaying it. Called null.

### holdout-0056 — `fever_present` = `true`

> The burning is severe today and I noticed visible dark red blood in the toilet bowl just now. I also have a sharp ache in my lower right back and chills, which is making me feel really unwell and worried it might have spread. Im not actually at home at the moment, so is it possible to get something sent to me here in London?

'chills' with no temperature stated. Called true.

### holdout-0060 — `dysuria_present` = `null`

> I think I have another UTI starting up. I get about two or three of these a year, and it always starts with this dull ache above my pubic bone and a constant pressure in my bladder. It doesn't hurt terribly yet when I pass urine, but I know from past experience it will get worse fast if I don't get antibiotics soon. Nitrofurantoin worked well last time

'doesn't hurt terribly yet when I pass urine' -- explicit partial denial. Called null, arguably false.

### holdout-0062 — `dysuria_present` = `true`

> I've noticed I'm needing to run to the toilet every 20 minutes today, though I only pass tiny amounts each time. There isn't much pain, just a strange irritation and discomfort right at the end of peeing. I haven't taken any medication yet, but it's getting very disruptive because I'm having to interrupt work meetings constantly.

'There isn't much pain, just a strange irritation and discomfort right at the end of peeing'. Called true.

### holdout-0063 — `recent_uti_present` = `false`

> For the past three days, my urine has been dark, cloudy, and unusually strong-smelling. I have a persistent, heavy ache in my lower bit of my tummy and I feel like my bladder never fully empties when I go. I finished a course of antibiotics for a chest infection two weeks ago, so I don't know if that's related, but drinking extra fluids hasn't cleared it up.

antibiotics two weeks ago but for a *chest* infection. Called false.
