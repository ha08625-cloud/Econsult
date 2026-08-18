# Cross-signal language in the fragment libraries — 2026-08-18

Output of `python -m scripts.synthetic_data --lint` (cross-signal section) against
the committed `data/synthetic/` tree, recorded here because it is the input to the
per-pair `null_on` declaration pass and it should not live only in a terminal
scrollback.

**Regenerated when the six `recent_uti` libraries landed.** The first version of this
file covered 42 libraries and 257 pairs; the seventh signal's libraries add both new
rows and new columns, so a stale grid would have sent the declaration pass into a
tree it did not describe.

**What a row is.** For each (library, signal) pair where the signal is not the
library's own, how many of the library's lines match that signal's lexicon.

**What a zero is.** Evidence of topical absence at 59%–91% lexicon recall, not
proof. The lint proposes `null_on` with basis `absent` for every silent pair; a
human still confirms the library's subject matter before that is committed. That
is one judgement per pair, not per line.

**What a hit is.** A decision, not a bug — leave the pair undeclared, declare
`null_on` with basis `policy` and a written reason, or rewrite the line. See
`arch_training.md` section 8.

**293 pairs across 48 libraries. 35 match at least one line, across 25 libraries. 258 are silent.**

## The pairs that match

### `nocturia_null_thirdparty` → `urinary_frequency_present` — 9/47 lines (19%)

* `[urine+times]` A woman at my church group said she passes urine several times before morning
* `[toilet+trips]` With her hip the way it is, four trips to the toilet before dawn isn't safe for my nan
* `[toilet+times]` The gentleman I care for needs the toilet several times before morning
* `[toilet+times]` My husband is up three times before morning for the toilet and it wakes me as well
* `[toilet+times]` Four times last night, Dad rang to tell me, all of them the toilet
* `[toilet+trips]` Two or three trips to the toilet is normal for my aunt at the moment
* `[bathroom+times]` Over the fence my neighbour was telling me she's at the bathroom three times a night
* `[bathroom+more/more than usual]` Is going to the bathroom at night more than usual a symptom of anything, only my partner has started
* `[wee+times]` The bloke I share a room with on site is awake two or three times for a wee

### `nocturia_true` → `urinary_frequency_present` — 8/54 lines (15%)

* `[wee+times]` It sounds daft written down but I could set my watch by it, half one and half four every night, both times for a wee, and then Im awake for the day at six
* `[wee+times]` I'm getting up two or three times a night for a wee
* `[bladder+keep needing]` My sleep is broken because I keep needing to empty my bladder in the early hours
* `[wee+more]` I was up twice in the night and once more before the alarm, all for a wee
* `[bathroom+trips]` Four trips to the bathroom between midnight and six this morning
* `[toilet+trips]` My nights are broken up with trips to the toilet, it's every night now
* `[loo+times]` woke at one, woke again at four, both times for the loo
* `[loo+times]` Two or three times between going to bed and getting up, I'm heading for the loo

### `nocturia_false` → `urinary_frequency_present` — 6/54 lines (11%)

* `[toilet+trips]` The nights have been completely normal, no toilet trips whatsoever
* `[wee+times]` My husband is up two or three times a night for a wee but I sleep straight through
* `[loo+trips]` no night time trips to the loo for me
* `[bathroom+trips]` I've been sleeping like a log, no trips to the bathroom at all
* `[toilet+times]` The baby has me up at two and five and I never need the toilet at those times
* `[loo+times]` When I was pregnant I was up three times a night for the loo, but I'm not now

### `dysuria_null_hedged` → `urinary_frequency_present` — 5/40 lines (12%)

* `[wee+times]` Sometimes there's a twinge when I wee and other times nothing at all, it's really inconsistent
* `[wee+more]` I might have noticed the stinging more when I wee because I was paying closer attention, hard to say now
* `[weeing+all the time]` Hard to say whether the pain is actually when I'm weeing or whether it's just there all the time
* `[weeing+regularly]` I'm taking paracetamol regularly so I've no idea whether weeing would be sore otherwise
* `[pass urine/urine+more]` I'd say it's more of a strange sensation than pain when I pass urine

### `urinary_frequency_false` → `nocturia_present` — 5/46 lines (11%)

* `[loo+trips]` Same number of trips to the loo as any other week.
* `[toilet+trips]` There's no extra trips to the toilet, that's not part of this.
* `[toilet+trips]` I looked out for it after reading the question and my toilet trips are unchanged.
* `[toilet+trips]` I'd say my toilet trips are unchanged, maybe fewer because I've been drinking less.
* `[wee+get up]` I haven't had to get up any more than usual for a wee.

### `nocturia_null_historical` → `urinary_frequency_present` — 4/46 lines (9%)

* `[loo+hourly/trips]` Hourly trips to the loo went on for weeks after my prostate op
* `[loo+trips]` My nights before the hysterectomy were nothing but trips to the loo
* `[toilet+trips]` My last job started so early that the toilet trips felt like part of the shift
* `[toilet+times]` When I was expecting my first I needed the toilet three or four times before morning

### `recent_uti_null_hedged` → `dysuria_present` — 4/44 lines (9%)

* `[loo+sting]` I felt a sting when I went to the loo last fortnight but I was using new bath salts so maybe it was just that.
* `[bladder+twinges]` I had some bladder twinges about ten days ago but drinking extra water seemed to stop it so I am not convinced.
* `[toilet+stinging]` I was stinging a bit when I went to the toilet three weeks ago but I had switched washing powder so I am not sure.
* `[wee+stingy]` My wee was stingy around three weeks ago but it might just have been from wearing tight jeans all day.

### `haematuria_null_hedged` → `fever_present` — 3/45 lines (7%)

* `[hot]` My urine went darker on that hot day walking and was back to normal by teatime.
* `[flushed]` The water looked pinkish but I dont think the last person flushed properly.
* `[flushed]` I think I saw blood but by the time I looked again I had already flushed.

### `nocturia_null_attribution` → `dysuria_present` — 3/51 lines (6%)

* `[toilet+pain]` It's the pain in my knee that has me out of bed, the toilet trip is just because I'm up
* `[loo+uncomfortable]` My leg ulcer dressing was uncomfortable and had me awake, so I used the loo while I was up
* `[toilet+cramp]` I get cramp in my calf in the night and once I'm out of bed I'll go to the toilet

### `urinary_frequency_null_hedged` → `nocturia_present` — 3/42 lines (7%)

* `[loo+trips]` Some days it feels like more trips to the loo, other days it doesn't.
* `[toilet+trips]` I've been anxious about all this so I may be reading too much into my toilet trips.
* `[toilet+trips]` Honestly unsure whether my toilet trips have gone up.

### `urinary_frequency_true` → `nocturia_present` — 3/46 lines (7%)

* `[loo+getting up]` I've been getting up from my desk every twenty minutes for the loo.
* `[toilet+trips]` My toilet trips have gone through the roof this week.
* `[bathroom+trips]` My step counter is mostly just trips to the bathroom at this point.

### `dysuria_true` → `nocturia_present` — 2/45 lines (4%)

* `[passing urine/urine+sleep]` I'm experiencing severe discomfort passing urine and it's affecting my sleep.
* `[weeing+night/waking]` I've been waking up at night because weeing is so painful.

### `flank_pain_false` → `dysuria_present` — 2/55 lines (4%)

* `[wee+uncomfortable]` My sides feel fine, it's just uncomfortable when I wee.
* `[urine+soreness]` There's no soreness in my back, just the usual urine symptoms.

### `haematuria_true` → `fever_present` — 2/45 lines (4%)

* `[flushed]` When I flushed I could see red swirling round the bowl.
* `[flushed]` The bowl was red before I flushed and then it was red again two hours later.

### `haematuria_true` → `urinary_frequency_present` — 2/45 lines (4%)

* `[pee+times]` Ive seen blood in my pee three times today.
* `[loo+times]` The last two times I have been to the loo the water has been pink.

### `nocturia_null_attribution` → `urinary_frequency_present` — 2/51 lines (4%)

* `[wee+more]` My insomnia has me awake anyway and I go for a wee out of boredom more than anything
* `[toilet+times]` The neighbour's car alarm went off twice last night and I went to the toilet both times because I was awake

### `recent_uti_true` → `dysuria_present` — 2/44 lines (5%)

* `[bladder+discomfort]` I assumed the discomfort ten days ago was thrush again but the sample showed a bladder infection.
* `[urine+ache]` I thought the ache after gardening a fortnight ago was a pulled muscle but the doctor found a urine infection.

### `urinary_frequency_null_thirdparty` → `nocturia_present` — 2/44 lines (5%)

* `[wee+getting up/night]` My grandad's been getting up four or five times in the night for a wee.
* `[toilet+night]` My other half would never book himself in, but he's up to the toilet four times a night.

### `dysuria_false` → `urinary_frequency_present` — 1/47 lines (2%)

* `[wee+more]` Nothing hurts when I wee, it's more a general feeling of being unwell.

### `dysuria_null_historical` → `flank_pain_present` — 1/38 lines (3%)

* `[back+sore]` I've had thrush before and the weeing was sore with it, but that was ages back

### `dysuria_null_historical` → `recent_uti_present` — 1/38 lines (3%)

* `[water infection+antibiotics]` I had antibiotics in March for a water infection, it burned to wee then

### `dysuria_null_thirdparty` → `nocturia_present` — 1/46 lines (2%)

* `[peed+slept]` Someone I slept with told me afterwards he'd had burning when he peed

### `dysuria_true` → `urinary_frequency_present` — 1/45 lines (2%)

* `[wee+constantly]` I've had this burning constantly when I go for a wee, it's been relentless.

### `flank_pain_null_historical` → `dysuria_present` — 1/40 lines (2%)

* `[urine+pain]` I used to get kidney pain every time I had a urine infection in my twenties.

### `flank_pain_null_thirdparty` → `recent_uti_present` — 1/47 lines (2%)

* `[uti+antibiotics]` My colleague had flank pain with her last UTI and needed antibiotics.

### `haematuria_false` → `fever_present` — 1/45 lines (2%)

* `[flushed]` I had a good look before I flushed and there was nothing red in there.

### `haematuria_null_hedged` → `urinary_frequency_present` — 1/45 lines (2%)

* `[wee+all day]` My wee was dark orange, almost brown, but I have barely drunk a thing all day.

### `haematuria_null_historical` → `dysuria_present` — 1/45 lines (2%)

* `[urine+hurt]` When I came off a ladder and hurt my back in 2021 I passed red urine.

### `haematuria_null_historical` → `flank_pain_present` — 1/45 lines (2%)

* `[back+hurt]` When I came off a ladder and hurt my back in 2021 I passed red urine.

### `haematuria_null_historical` → `recent_uti_present` — 1/45 lines (2%)

* `[urine infection+treated]` Ten years ago I was treated for a urine infection that gave me blood in my wee.

### `haematuria_null_historical` → `urinary_frequency_present` — 1/45 lines (2%)

* `[wee+all day]` I used to get blood in my wee now and then in my old job lifting all day.

### `haematuria_null_thirdparty` → `nocturia_present` — 1/45 lines (2%)

* `[weeing+night]` My son mentioned his housemate was weeing red after a night out.

### `nocturia_null_attribution` → `haematuria_present` — 1/51 lines (2%)

* `[bathroom+blood]` My blood sugar drops at night so I'm up for a biscuit and I use the bathroom while Im down there

### `nocturia_null_metaphor` → `dysuria_present` — 1/52 lines (2%)

* `[wee+kick]` Ive written a wee note to bring with me because I can never remember everything when Im sat in the room with the doctor and then I kick myself the whole way home

### `recent_uti_null_hedged` → `urinary_frequency_present` — 1/44 lines (2%)

* `[wee+all day]` My wee was stingy around three weeks ago but it might just have been from wearing tight jeans all day.

## The libraries with no matches at all

23 libraries are silent about every signal that is not their own:

* `dysuria_null_metaphor`
* `emotional`
* `expectations`
* `fever_false`
* `fever_null_attribution`
* `fever_null_hedged`
* `fever_null_historical`
* `fever_null_metaphor`
* `fever_null_thirdparty`
* `fever_true`
* `flank_pain_null_hedged`
* `flank_pain_true`
* `justifiers`
* `nocturia_null_hedged`
* `recent_uti_false`
* `recent_uti_null_adjacent`
* `recent_uti_null_historical`
* `recent_uti_null_thirdparty`
* `tangents`
* `urinary_frequency_null_adjacent`
* `urinary_frequency_null_historical`
* `urinary_frequency_null_metaphor`
* `uti_speculation`
