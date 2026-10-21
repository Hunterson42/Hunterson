# Reference selection record

Working record for choosing and monitoring the reference checkpoint for each grade. Kept in the repository so that every selection decision has a dated, public trail. Nothing here is published; the methodology is the published document.

Last updated: 20 October 2026.

---

## 1. Decisions taken

### 1.1 Grade boundary: 30B active parameters

Standard is 30 billion active parameters or fewer. Heavy is above 30 billion.

**Rationale.** Active parameters, not total, determine cost and speed, because only the active portion is used per token. The models observed cluster at 5.1B, 13B and 18B active, then jump to 32B, 40B and 49B. The line sits inside that empty band.

**Why 30 and not 32.** GLM-4.5, a previous-generation model, has exactly 32B active, and Kimi K2.6 has exactly 32B. A boundary with models sitting on it is unanswerable in argument. 30B keeps a 12B gap below and a 2B gap above.

**Review trigger.** The boundary is reviewed whenever a model appears within 20 per cent of it, that is between 24B and 36B active. Kimi K2.6 at 32B is inside that band, so the review is on the record from launch, dated before any assessment is published.

**Known soft edge.** The Qwen dense 27B models would fall in Standard on active parameters while pricing at roughly $2.50 per million, five times the Standard band. Active parameters predict the price band well but not perfectly. Not retrofitted: the rollover mechanism and its published conversion ratio exist to carry users across exactly such a step. Recorded here as a known limitation. Confirm whether these models are dense before writing it up.

### 1.2 Frontier grade: definition

Frontier comprises open-weight models at the capability edge, provisionally
those above 70 billion active parameters.

**The 70 billion floor is provisional.** It sits in the gap between DeepSeek
V4 Pro at 49B active and Qwen 3.8 at 95B, but it rests on two observations
where the 30B line rested on seven. It will be reviewed once five models sit
above it.

**What actually defines the grade is serving fragmentation, not size.** At
1.7T total, DeepSeek V4 Pro has eight providers all at fp8, because the lab
published at fp8 and everyone serves it that way. Kimi K3 at 2.8T has
seventeen providers across five tags. Size does not fragment a panel; being at
the capability edge does, because that is where providers are forced into
their own compromises to serve economically.

**Correction, 17 September.** This section previously concluded Frontier was
unpublishable because no model reached five providers at one precision. That
rested on reading the ranking page's tag split as though each tag were a
different product. Once Kimi K3's native precision was resolved to mxfp4 from
config.json, fp4 and mxfp4 became one population under rule 1.3, and K3 shows
6 qualifying providers on every day from 11 to 16 September and 7 on the 17th.
The finding was wrong and the grade has a panel.

**Frontier is nonetheless not published at launch.** See rule 1.4.

### 1.3 Precision tag equivalence

Where a lab publishes a checkpoint in exactly one quantised format, provider
tags naming the bit width without the variant are treated as that format.
Where a lab publishes in more than one format, only the exact tag qualifies.
The accepted tags for each reference are listed in the methodology and cannot
be changed without a published change note.

**Why this rule exists.** gpt-oss-120b and Kimi K3 are both published solely in
mxfp4 form, confirmed from config.json, yet most providers tag them bare fp4.
Insisting on the exact tag gave gpt-oss a panel of zero, which is absurd for a
model published in only one form. The rule is general rather than decided case
by case, and the accepted tags are published so that widening them to reach
five providers is visible.

**Observed convention.** Both OpenAI and Moonshot publish very large MoE models
as 4-bit routed experts on a bfloat16 skeleton, with attention, shared experts,
dense projections, the output head and any vision tower left unquantised. This
appears to be becoming the default release format at the top end.

**Warning on page tags.** The "8-bit precision" tag on Hugging Face is inferred
and is wrong for compressed-tensors models. It appears incorrectly on both
gpt-oss-120b and Kimi K3. config.json governs.

### 1.4 Launch threshold and maintenance floor

**Launch threshold.** A grade is published only after its reference has held at
least 10 qualifying providers for 20 consecutive assessment days.

**Maintenance floor.** Once published, the grade continues while the reference
holds at least 5. Below 5, no price is published that day and the count is
published instead, with the reason. A grade below 5 for 20 consecutive days is
withdrawn and must re-qualify at the launch threshold.

**Why two numbers.** This is the exchange convention: listing requirements are
stricter than continued listing requirements. A grade admitted at exactly the
floor is one departure from non-publication, and a grade that prints "not
published" every third week looks like a failure rather than a rule working.

**Position at 17 September.** Standard qualifies, reference at 15. Heavy
qualifies, reference at 13. Frontier does not, reference at 6 or 7.

**Consequence.** Standard and Heavy launch on 3 November. Frontier publishes a
daily qualifying count with no price until it reaches 10. The count is
published rather than withheld, because the number of providers able to agree
on how to serve a frontier open-weight model is itself a measure of how
commoditised the top of the market is.

**Amendment, 2 October: Heavy is not launched as a priced grade.** Heavy is
published at launch as a daily qualifying count with the reason, on the same
footing as Frontier. `candidates.json` marks the grade "not published" from
2 October, which moves it out of the headline figures on the site.

**Why.** The reference, GLM-5.3, has fallen from 13 qualifying providers to 11
and has been led for two consecutive days by GLM-5.2, the model it supersedes.
GLM-5.2 also led on 12 and 13 September and has tied the reference on eight
other days. A grade whose reference cannot hold a lead over its own predecessor
is not yet a settled product.

**This is a judgement, and the rule does not yet say it.** On the threshold as
written above, Heavy qualifies: its reference has held at least 11 on every one
of 22 census days. The exclusion needs a stated rule before methodology 1.0, or
it is discretion. Two wordings have been considered:

- "The reference has not declined across the qualifying window." Not usable as
  worded, because the answer depends on the day the window starts. GLM-5.3 was
  at 13 on 11 September and at 11 on 13 September.
- "No challenger has a running lead over the reference at launch." Well defined
  and readable straight from `data/track.md`, but it would also hold back
  Standard on a one day wobble, so it would need a minimum streak before it
  bites.

Open item 3 carries this.

**Consequence, replacing the one above.** Standard launches on 3 November.
Heavy and Frontier publish a daily qualifying count with no price.

### 1.5 The census is written once per day

`census.py` refuses to overwrite a day's census once written. A manual re-run
skips collection and re-runs only the analysis.

**Why.** Before this change, the folder was named for the date but its contents
were whatever the last run of the day had fetched. Between a 12:03 and a 15:47
run on 17 September, the 17 September census changed: DeepSeek V4.1-Flash went
from 8 qualifying providers to 9, Kimi K3 from 6 to 7.

Harmless in selection work and fatal once live. The assessor takes posted
prices from that day's census, and the methodology says prices are taken in a
fixed window. A later run overwriting the morning's file would mean the
published price was marked against data that did not exist at the assessment
time, and the raw data would no longer support the number.

Re-analysing is free. Re-collecting is not.

### 1.6 Reference selection before first publication

Recorded 2 October 2026.

**Rule.** Until the first assessment is published, the stickiness test alone
selects the reference. A challenger that holds more qualifying providers than
the reference on 20 consecutive census days becomes the reference on the
twentieth day. There is no parallel period and no conversion ratio.

**From first publication onward** the full rollover procedure applies: 20
consecutive leading days, then 30 assessment days of parallel publication with
the ratio between the two published daily.

**Why.** Parallel publication protects people who rely on a published number.
Before launch nobody does, so there is nothing to convert and nobody to give
notice to.

**What it replaces.** A review on 25 September proposed fixing the reference on
that date, freezing it through the shadow period and starting the stickiness
clock at first publication. That proposal was never recorded in this file and
is not adopted. Under it, a reference that had already been overtaken would
launch on 3 November with a rollover certain, and the parallel period would
fall in the first weeks of the series.

**No discretion.** The `reference` flag in `candidates.json` changes only when
`data/track.md` reports the trigger for that grade, and it is changed on that
day. Leading means strictly more qualifying providers. A tie breaks the streak,
which is how the tracker already computes it.

**Position when recorded.** The Standard reference is GLM-5.3-Flash. DeepSeek
V4.1-Flash tied it on 29 September and has led on 30 September, 1 October and
2 October, 3 of 20. If the lead is unbroken, the trigger falls on the census of
19 October. If it breaks, the count restarts. This rule is recorded before
either outcome is known.

**Scope.** Standard only for now. Heavy and Frontier are not being launched
(rule 1.4), and a Heavy reference overtaken by the model it supersedes is
treated as evidence against launching the grade, not as a reason to adopt the
older model.

**Consequences for the build.**

- Provider accounts are opened to cover both checkpoints. Nine providers serve
  both at fp8 on 2 October (section 2, reading of 2 October).
- The shadow probe runs against both, so a change of reference before launch
  costs no shadow days.
- Methodology 1.0 names the reference this rule gives on the day it is frozen,
  and states the rule.

### 1.7 Decisions of 14 October

Recorded 14 October 2026. Seven decisions, taken together, on the
recommendations in roadmap version 6, section 1.4.

**D1. Route.** Hybrid. Every assessed observation is bought through
OpenRouter, pinned to one provider endpoint by its tag, with fallback switched
off. Six direct accounts run alongside as a control group: Novita, GMI Cloud,
SiliconFlow, BaseTen, Z.AI and DeepInfra. The control group never enters the
assessed figure.

**D2. Pricing basis.** The price listed for the pinned endpoint during the
delivery window, confirmed by the cost on the receipt to within one per cent.
Promotional discounts open to any buyer are included, and the figure with
discounts removed is published beside it. The venue's fee for buying credit is
excluded and stated. A provider whose receipt does not match is excluded that
day, with the reason published.

**Why D1 and D2.** On 2 October Novita listed GLM-5.3-Flash at $0.28 output
on OpenRouter and $0.50 on its own site. Testing direct while taking the price
from the listing, as version 4 planned, would have published a price nobody
paid. Price and delivery must be observed in the same place.

**D3. Launch threshold, amended.** A grade is first published only after the
checkpoint that is its reference has, on each of the last 20 consecutive census
days, held at least 10 qualifying providers and at least as many as every other
candidate in its grade. The days count whether or not the checkpoint was the
reference on them. This replaces the judgement recorded in the amendment to
rule 1.4 of 2 October with a rule. Census days, not assessment days. Every
model on the tracker's watchlist is placed in a grade or on the ignore list
within ten working days, because the rule depends on the candidate list being
complete.

**D4. Email on old commits.** Email privacy to be switched on in GitHub. The
existing commits are not rewritten unless the pseudonym is to be kept separate
from the owner's name, and in that case only before first publication.

**D5. DeepSeek V4.1-Flash.** Accepted tag `fp8` only. Providers tagged plain
`fp4` are excluded until they confirm in writing that they serve the published
form, fp8 with fp4 experts. Where a model card states two active parameter
figures, the larger governs: for this model, 16B during decode, not 8B during
prefill.

**D6. Launch on a gate.** The first assessment is published on the first
weekday on which all nine conditions in roadmap version 6, section 1.2, hold.
3 November was the target; on 14 October the realistic date became 5 November
at the earliest.

**D7. Frontier.** Not probed in shadow for now. A grade is launched only after
it has met the launch threshold and completed its own shadow period. Frontier
shadow probing to be reconsidered in November if Kimi K3 still holds 10 or
more. The same applies to Heavy.

### 1.8 A reference must allow thinking to be switched off

Recorded 14 October 2026, decision D8.

**Rule.** A checkpoint can be a reference only if its thinking mode can be
switched off. Eligibility is read each day from the census listing, field
`reasoning.mandatory` in `models.json`, and shown in `data/track.md`.
Checkpoints with mandatory thinking stay in the tracker but cannot be chosen,
and cannot trigger a change of reference however long they lead.

**Why.** The specification requires thinking to be off, because thinking
tokens are billed as output tokens. With thinking on, the same job would cost
an unpredictable amount more from one provider to the next, and the price
would stop comparing like with like. Allowing thinking at its lowest setting
was considered and rejected for the same reason.

**What found it.** The first probe test on 14 October. Every request for
GLM-5.3-Flash failed with "Reasoning is mandatory for this endpoint and cannot
be disabled", while DeepSeek V4.1-Flash passed with no thinking tokens. The
listing marks GLM-5.3-Flash `mandatory: true`, and has done on every census
day since 11 September. It was not checked when GLM-5.3-Flash was chosen.

**Candidates affected, from the listing on 14 October.** Thinking mandatory:
GLM-5.3-Flash, gpt-oss-120b, GLM-5.3 and Qwen 3.8 (2.4T). All other
candidates can switch it off.

**Consequences, applied 14 October.**

- Standard: DeepSeek V4.1-Flash becomes the reference now, by this rule, not
  on 19 October by rule 1.6. It has led GLM-5.3-Flash every day since
  30 September and leads every eligible candidate
- Heavy: GLM-5.2 becomes the reference. The grade remains unpublished
- The probe covers DeepSeek V4.1-Flash and DeepSeek V4 Flash 0731, the next
  eligible Standard checkpoint, so a second model stays in shadow
- Rule 1.6 continues to apply between eligible candidates

### 1.9 The frozen test piece

Recorded 14 October 2026.

`prompt.txt` is frozen at SHA-256
`140afc12e0c154fd2cb843197da5d3bc673c9e1cea6e0585236b2f41a2a8b24a`: the
instruction block, Act 1 Scene 2 of The Tempest and the opening of Act 2
Scene 1 (Project Gutenberg ebook 1540), ending on a speech by Sebastian. It
measured 7,613 input tokens on DeepSeek V4.1-Flash. The acceptance strings are
`ISLAND DUKE Prospero` and `LAST SPEAKER Sebastian`, compared without regard
to letter case, because the play prints names in capitals.

### 1.10 Decisions of 15 and 16 October

Recorded 20 October 2026, with the methodology pull request. Taken on 15 and
16 October and kept until now in the roadmap and the methodology checklist.

**Methodology, 15 October.**

- **D9. Correctness.** Every completed request must give both acceptance
  strings as its first two lines and stop at the 500-token limit. Two of three
  is not enough
- **D10. Blended price.** The blend, 16 input to 1 output, of the two
  interquartile means, not the mean of each provider's blend
- **D11. Window.** Every scheduled weekday is a window. A day with no probe
  counts as a failure for every provider and breaks the run of five
- **D12. Rounding.** Computed from unrounded per-token prices; published in
  US dollars per million to four decimal places, halves rounded up
- **D13. The five.** Counted in contributors, both for not publishing a day
  and for withdrawing a grade after 20 assessment days below five. Amends the
  maintenance floor in rule 1.4, which counted qualifying providers
- **D14. Emergency clause kept.** If the old reference has fewer than five
  contributors on five assessment days in a row during a parallel period, the
  period ends on its tenth assessment day, or at once if that has passed
- **D15. Producer.** "Malcolm Hunter (a pen name), trading as Hunterson"
- **D16. "Every other candidate"** in D3 means every other eligible candidate

**Response to the venue, 15 October.**

- **D17. Raw responses not published.** The census, the probe's listing
  snapshots and test records, and the rehearsals are kept privately. One
  SHA-256 manifest per raw day is published, written once
- **D18. Public history cleaned** by renaming the repository to
  `Hunterson-raw`, making it private, and creating the public `Hunterson` from
  a filtered copy of the history
- **D19. Price on receipts.** Each contributor's price is the receipt's cost of
  input, and of output, divided by the tokens counted. The listing is the check
- **D20. Written request** to the venue's sales team, narrow: the daily reading
  of the public listings, and derived figures with attribution. No raw
  republication
- **D21. Launch condition restated.** Launch does not wait on written
  permission from the venue; the risk is accepted knowingly and the
  methodology states the position as it stands

**Operations and publication, 16 October.**

- **D22. The census is taken by the London server at 06:15 UTC,** with
  GitHub's workflow as the backup from 06:41
- **D23. Only the mirror writes to the public repository**
- **D24. Domain `hunterson.org`;** contact `malcolm@hunterson.org`
- **D25. The price pages' design:** the output price as the headline, change
  shown without colour, a permanent page for each day, each provider's price
  shown, the shadow period shown and labelled
- **D26. Assessments stay private until the first publication**
- **D27. The grade is in every address from the first day,**
  `hunterson.org/GRADE/YYYY-MM-DD/`, and the downloadable data carries a grade
  column
- **D28. Readings outside the window, for research only.** The same test at
  weekends and at a random hour each day, kept privately in
  `data/offwindow/`, fingerprinted, and never part of the assessment, the
  reliability test or the run of five

### 1.11 Count independent sources, not names

Recorded 19 October 2026, decision D29.

**Rule.** Providers that resell inference served by another listed provider or
by a common network, or that are under common control, form a group. A group
counts as one provider in the qualifying count, and so in the choice of
reference and the launch threshold, and once in the contributor count for the
floor. In the price it gives one observation: that of the member with the
lowest output price paid, with its input price, among the members that pass
every test. Providers that rent GPUs from the same cloud, or run the same
serving software, are not a group.

**How a group is recorded.** On public evidence only, in `affiliations.json`,
with the evidence and the day it applies from, which is later than the day it
is recorded. Never applied backwards. Built into `scripts/assess.py` and
`scripts/track.py` on 19 October; the register is empty.

**Why now.** Written before any case has arisen, so that it is in methodology
1.0. A compute network planning to list on the gateways through several brokers
in the first quarter of 2027 would otherwise add several observations from one
source. Illustrative figures: ten independent providers at $0.85 and four
resellers of one network at $0.40 give $0.7938 counted by name and $0.8500
counted by source.

### 1.12 Speed limits, from windows 1 to 4

Recorded 20 October 2026, with the methodology pull request.

**Rule.** A provider passes the speed test if the median first-token time of
its completed requests is within 3 seconds and their median speed, from the
first token, is at least 30 output tokens per second. Replaces the provisional
2 seconds.

**Evidence.** In windows 1 to 4, several DeepSeek V4 Flash 0731 providers sat
between 2 and 3 seconds to the first token, and which of them fell over the
line changed from day to day. Unofficial figures, reliability set aside:

| Window | 0731 at 2 seconds | 0731 at 3 seconds |
|---|---|---|
| 15 October | 8 contributors, $0.4163 | 9, $0.4650 |
| 16 October | 6, $0.2510 | 9, $0.4168 |
| 19 October | 4, no price | 6, $0.4040 |
| 20 October | 5, $0.5959 | 9, $0.4948 |

At 3 seconds the figure stayed between $0.40 and $0.49 with a price every day;
at 2 seconds it ran from $0.25 to $0.60 and once had none. The limit changed
neither DeepSeek V4.1-Flash nor V4.1-Flash-1017 in any window. Providers
genuinely slow, at 3.5 to 25 seconds, are excluded either way. The speed floor
of 30 tokens a second excluded Morph once (27, on 19 October) and Mancer 2 on
0731 at 23 to 25; it is unchanged.

### 1.13 Every fingerprint is timestamped by two independent services

Recorded 21 October 2026 (decision D33), with the timestamp pull request.

**Rule.** When a fingerprint file is written, its hash is sent at once to
OpenTimestamps, which anchors it in the Bitcoin blockchain within a few hours,
and to FreeTSA, which signs it within seconds under RFC 3161. Both proofs are
published beside the fingerprint and kept in both repositories. Each
assessment is fingerprinted, one fingerprint per file, and stamped when the
assessor commits it, which is before publication. A proof is written once; an
OpenTimestamps proof is completed once, when its Bitcoin block confirms, and is
otherwise never changed. A request that fails is retried on the next run and
recorded; it never stops the mirror or a publication. Only hashes leave the
machine.

**Evidence.** A fingerprint proves content, not date: git records whatever
time a commit states. The public repository was deleted and recreated on
16 October, so nothing in it independently shows when a fingerprint first
appeared, and until this rule the fingerprints existed only there. Methodology
0.9 promised a cryptographic timestamp in square brackets. Two services,
because each covers the other's weakness: the authority signs at once but
rests on trusting its key; the Bitcoin anchor needs no trust in anyone but
takes hours.

**Why one fingerprint per assessment file.** The assessor writes each
checkpoint's file once, but can add a file to an earlier day, for example when
a checkpoint is placed after its windows ran. One fingerprint per day would
then change, and stop the mirror; one per file makes the addition a new
fingerprint.

**Limit.** Fingerprints written before the first run were stamped on it, and
prove existence from then, not from the day of their records. The moment is
recorded in `data/hashes/stamping-began.txt`.

---

## 2. Daily tracking

Generated automatically into `data/track.md` by `scripts/track.py`. That file
rebuilds the full history from the saved census on every run and computes the
20-day stickiness streak for each challenger. Read it rather than transcribing
counts by hand.

**Counting rule.** Qualifying count means DISTINCT PROVIDERS serving the
checkpoint at an accepted precision. The ranking page in `data/rank/` counts
ENDPOINTS, which is a larger number because several providers list the same
model twice. The selection rule uses providers. Any figure taken from the
ranking page is wrong for this purpose.

### Standard grade, qualifying providers

| Date | GLM-5.3-Flash | DS V4-Flash-0731 | DS V4.1-Flash | gpt-oss-120b |
|---|---|---|---|---|
| 11 Sep | 14 | 11 | 6 | 6 |
| 12 Sep | 15 | 11 | 8 | 6 |
| 13 Sep | 15 | 11 | 8 | 6 |
| 14 Sep | 16 | 12 | 9 | 6 |
| 15 Sep | 16 | 11 | 8 | 6 |
| 16 Sep | 15 | 12 | 9 | 7 |
| 17 Sep | 15 | 12 | 8 | 7 |

Accepted precisions: fp8 for the GLM and DeepSeek models; mxfp4 or fp4 for
gpt-oss-120b.

### Heavy grade, qualifying providers

| Date | GLM-5.3 | GLM-5.2 | DS V4-Pro-0813 | Kimi K2.6 |
|---|---|---|---|---|
| 11 Sep | 13 | not tracked | 8 | precision unresolved |
| 12 Sep | 11 | not tracked | 8 | precision unresolved |
| 13 Sep | 11 | not tracked | 8 | precision unresolved |
| 14 Sep | 12 | not tracked | 8 | precision unresolved |
| 15 Sep | 13 | not tracked | 8 | precision unresolved |
| 16 Sep | 13 | not tracked | 8 | precision unresolved |
| 17 Sep | 13 | 12 | 8 | precision unresolved |

GLM-5.2 added to the candidate set on 17 September after appearing on the
watchlist. Earlier days will populate on the next run, since the tracker
rebuilds from the saved census.

### Reading, 17 September

**No challenger has led either reference on any day.** The stickiness rule has
not come close to triggering in seven days, including a week in which a new
model was released into the Standard band.

**Daily variation is plus or minus one provider.** This is endpoints appearing
and disappearing rather than providers entering or leaving. A 20 consecutive
day requirement absorbs that comfortably, which is the first evidence the rule
produces a stable reference rather than a jittery one. Worth a sentence in the
methodology, because it is the first thing a reader will doubt.

**Standard: the lead is flat, not widening.** GLM-5.3-Flash gained two
providers and gave one back, ending at 15. DeepSeek V4 Flash 0731 gained one
and held it, ending at 12. The gap touched four on 14 and 15 September and is
back to three.

**The slow climb is the thing to watch.** DeepSeek V4 Flash 0731 has added
roughly one provider a week while the reference has added none. At that rate
the gap closes in about three weeks, which would put the stickiness rule to
work in late October, just as the shadow period ends.

**DeepSeek V4.1-Flash is not behaving as a challenger.** It was already in the
census on 11 September at 6 providers, not a new arrival as first thought. It
has oscillated between 8 and 9 since 12 September with no upward trend in five
days, and sits seven behind the reference. Whatever adoption it was going to
get on release, it has had.

**Heavy is stable to the point of stagnation.** GLM-5.3 dipped to 11 mid-week
and recovered to 13, ending where it started. DeepSeek V4 Pro 0813 has not
moved at all in seven days, which suggests a settled panel rather than a
growing one.

**GLM-5.2 at 12 is the Heavy concern.** A superseded model retaining almost the
same panel as its replacement means providers are not migrating. If the Heavy
reference is GLM-5.3 at 13 and its own predecessor sits at 12, the reference is
less secure than the headline gap to DeepSeek suggests.

### Corrections to earlier entries

Figures recorded before 17 September were endpoint counts taken from the
ranking page and were overstated. GLM-5.3-Flash was recorded as 16 on 14
September and 18 on 17 September; the correct qualifying provider counts are
16 and 15. DeepSeek V4 Flash 0731 was recorded as 13 on both dates; the
correct counts are 12 and 12. GLM-5.3 was recorded as 12 then 15; the correct
counts are 12 and 13. Every candidate block in sections 3 to 5 needs the same
correction applied.

### Reading, 2 October

Twenty-two census days, 11 September to 2 October, with no gaps. Figures are
qualifying providers from `data/site/track.json` as generated at 06:11 UTC on
2 October.

**Gap in this record.** Nothing was written here between 17 September and
2 October. A review took place on 25 September but its conclusions were not
recorded at the time, so nothing in this file should be read as a decision
dated 25 September. For the record, the census shows GLM-5.3-Flash ahead of
every Standard challenger on each of the 15 days to 25 September, at 14 against
13 and 13 on that day.

| Grade | Model | 11 Sep | 17 Sep | 25 Sep | 29 Sep | 30 Sep | 1 Oct | 2 Oct |
|---|---|---|---|---|---|---|---|---|
| Standard | GLM-5.3-Flash (reference) | 14 | 15 | 14 | 15 | 15 | 14 | 13 |
| Standard | DeepSeek V4.1-Flash | 6 | 9 | 13 | 15 | 16 | 15 | 15 |
| Standard | DeepSeek V4 Flash 0731 | 11 | 12 | 13 | 13 | 12 | 12 | 12 |
| Heavy | GLM-5.3 (reference) | 13 | 13 | 11 | 11 | 11 | 11 | 11 |
| Heavy | GLM-5.2 | 13 | 12 | 11 | 11 | 11 | 12 | 12 |
| Heavy | DeepSeek V4 Pro 0813 | 8 | 8 | 9 | 10 | 9 | 9 | 9 |
| Frontier | Kimi K3 (reference) | 6 | 7 | 7 | 8 | 9 | 9 | 9 |

**Standard: the reference has been overtaken.** DeepSeek V4.1-Flash has gone
from 6 qualifying providers to 15 in three weeks, peaking at 16 on
30 September. It tied the reference on 29 September and has led on each of the
three days since. GLM-5.3-Flash peaked at 16 on five days in September and is
now at 13, its lowest of the record.

**The 17 September reading of V4.1-Flash was wrong.** It said the model "is not
behaving as a challenger" and that "whatever adoption it was going to get on
release, it has had". It had 9 qualifying providers then and has 15 now.

**Heavy: the reference is being led by the model it supersedes.** GLM-5.2 is at
12 against GLM-5.3 at 11 on 1 and 2 October. It also led on 12 and
13 September. See the amendment to rule 1.4.

**Frontier is one provider short of the launch threshold.** Kimi K3 held 7 from
17 to 28 September, then moved to 8 on 29 September and 9 from 30 September.
Providers at any precision rose from 17 to 19 over the same days. It would need
to reach 10 and hold it for 20 days.

**Native share keeps falling for the older references.** Qualifying providers
as a share of all providers serving the model:

- GLM-5.3-Flash: 14 of 25 on 11 September, 56 per cent. 13 of 32 on 2 October,
  41 per cent
- GLM-5.3: 13 of 27, 48 per cent. Now 11 of 31, 35 per cent
- DeepSeek V4.1-Flash: 15 of 30, 50 per cent
- gpt-oss-120b: 5 of 20, 25 per cent, and exactly at the floor of 5 on all 22
  days

New serving capacity keeps arriving for the older models, and it keeps arriving
below native precision or undeclared.

**Panel overlap between the two leading Standard checkpoints, 2 October.**

- fp8 for both, 9 providers: AtlasCloud, BaseTen, GMICloud, Io Net, Morph,
  NextBit, Novita, SiliconFlow, StreamLake
- fp8 for GLM-5.3-Flash only, 4: Inceptron, Near AI, Phala, Z.AI
- fp8 for DeepSeek V4.1-Flash only, 6: Baidu, CoreWeave, DeepInfra, Makora,
  Parasail, Venice

Nineteen accounts cover both panels in full.

**Posted price context, not an assessment.** Taking each fp8 provider's lowest
posted output price on 2 October, in US dollars per million tokens:

- GLM-5.3-Flash: median 0.45, range 0.28 to 0.70, 13 providers
- DeepSeek V4.1-Flash: median 0.84, range 0.37 to 1.50, 15 providers

A change of reference would move the level by a factor of about 1.9. After
launch the published conversion ratio would carry that step. Before launch
there is nothing to convert, which is the case for settling the reference
first under rule 1.6.

**Corrections to the 17 September tables above.**

- gpt-oss-120b should read 5 on every day from 11 to 17 September. The 6 and 7
  shown were written before the tracker ran with the accepted tags for that
  model
- DeepSeek V4.1-Flash on 17 September reads 9 in the saved census. The 8 shown
  came from an earlier run the same day, before rule 1.5 made a day's census
  immutable

---

## 3. Standard grade candidates

### 3.1 zai-org/GLM-5.3-Flash

- OpenRouter id: `z-ai/glm-5.3-flash`
- Commit hash: `eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`
- Parameters: 321B total (Safetensors), 18B active (model card)
- Native precision: **fp8**. Tensor types F8_E4M3 bulk, with BF16 and F32 components. Card tag: fp8
- Licence: MIT
- Census 17 Sep: 29 providers, 30 endpoints. fp8 18, unknown 8, fp4 3, nvfp4 1. **Qualifying: 15**
- Hugging Face serving partners: Zai, Together, Novita, Fireworks, DeepInfra, Baseten
- Watch: chat template changed at commit `690b705` after release. Template changes are material under the methodology; weight changes have not occurred

### 3.2 deepseek-ai/DeepSeek-V4-Flash-0731

- OpenRouter id: `deepseek/deepseek-v4-flash-0731`
- Commit hash: `7872f01b1d1fe23eabc4c98b48bffcef5a386062`
- Parameters: 304B total (Safetensors, includes DSpark speculative decoding module), 284B main model (technical report), 13B active (technical report, arXiv:2606.19348 abstract)
- Report caveat: the report describes the April preview; the 0731 card states the same structure plus the DSpark module
- Native precision: **fp8**, per card tags. Tensor types BF16, I64, F32, F8_E4M3, I8
- Checked 2 October: `config.json` `quantization_config` gives quant_method "fp8", fmt "e4m3", weight_block_size 128 by 128, with no `expert_dtype` key. Confirms fp8. It does not explain the open question on repository size below
- Licence: MIT
- Census 17 Sep: 27 providers, 29 endpoints. fp8 13, unknown 9, fp4 6, bf16 1. **Qualifying: 12**
- Hugging Face serving partners: Together, Novita, Fireworks, DeepInfra, Baseten, Scaleway
- Alias warning: the undated `deepseek/deepseek-v4-flash` is a separate listing with 16 providers. Not the same product. The hash is the identifier
- Open question: repository is 167 GB against 304B parameters, which does not reconcile at one byte per parameter. Check `config.json` for a `quantization_config` block

### 3.3 openai/gpt-oss-120b

- OpenRouter id: `openai/gpt-oss-120b`
- Commit hash: `b5c939de8f754692c1647ca79fbf85e8c1e70f8a`
- Parameters: 117B total (card and Safetensors agree), 5.1B active (card)
- Native precision: **mxfp4**, not fp8. Expert weights published at four bits, stored as U8; remaining layers BF16. Designed to fit a single 80GB GPU in this form. The automatic "8-bit precision" tag is wrong for this model; the specific `mxfp4` tag governs
- Licence: Apache 2.0
- Census 17 Sep: 20 providers, 24 endpoints. unknown 9, fp4 6, bf16 5, fp8 3, fp16 1. **Qualifying at mxfp4/fp4: 6**
- Hugging Face serving partners: Together, Scaleway, OVHcloud, Nscale, Novita, Groq, Fireworks, Featherless, DeepInfra, Cerebras, Baseten
- Note: providers declaring bf16 are serving an upconverted version, not a shrunk one. Still not the published product
- Sibling: gpt-oss-20b, 21B total, 3.6B active

### 3.4 deepseek-ai/DeepSeek-V4.1-Flash

Card collected on 2 October 2026 from the Hugging Face repository page, its
`config.json` and its commit history. Confirm the commit hash by hand from
Files and versions before it is used as a reference identifier.

**Reading, 15 October 2026.** The commit hash pinned for the reference is
`5254448103b6254fc646dacbca1cbbf20e9216c1`, the head on 15 October, confirmed
by hand. The four commits after `2cba9e4`, all of 12 October, read one by one:
`8b3cec7` and `4dd75a8` change only the maker's example inference code
(`inference/model.py`, `inference/requirements.txt`); `4dd75a8` also adds
Python cache files, which `12b5c3a` deletes; `5254448` adds a `.gitignore`.
None touches the weights, `config.json`, the tokenizer files or the chat
template. Immaterial under the methodology's rule on example code.

- OpenRouter id: `deepseek/deepseek-v4.1-flash`
- Commit hash: `2cba9e42aa026125f3ed06c6d98c1db82f7ca027`, the head on 2 October, "Adding chat template (#68)", shown as one day old
- Commit history: 12 commits. Weights uploaded about 10 September at `678ae2a`. `config.json` unchanged since `517ef62` of the same date
- Parameters: 552B backbone (model card). 763B in the Safetensors box. The difference is not reconciled; `config.json` shows components outside the backbone: Engram embedding tables, a DSpark speculative decoding module and a vision tower
- Active parameters: **8B per token during prefill, 16B during decode** (model card). Standard on either figure
- First candidate to state two active figures. The grade definition needs a line saying which governs. Decode is the larger and is the one that applies to output tokens
- Architecture: MoE, 384 routed experts, 6 per token, 1 shared, 40 layers, hidden 5120. Context 1,048,576. Vision tower of 32 layers; the card is tagged Image-Text-to-Text
- **Native precision: fp8 with fp4 experts.** `config.json` `quantization_config` gives quant_method "fp8", expert_dtype "fp4", weight_block_size 32 by 32, scale_fmt "ue8m0", activation_scheme "dynamic". Base dtype bfloat16. Tensor types BF16, F32, F8_E4M3, I8. Card tags: fp8 and 8-bit precision
- Mixed precision is new in this series. The V4 Flash 0731 config has no `expert_dtype` key
- **Accepted tag: fp8, provisional.** It is the lab's own label for the release and the tag the tracker has counted since 11 September
- Decision needed before this checkpoint could be a reference: whether endpoints tagged bare fp4 are serving the published form, whose experts are fp4, or a four-bit requantisation of the whole model. A separate `nvidia/DeepSeek-V4.1-Flash-NVFP4` repository is listed on Hugging Face, so four-bit tags cannot be assumed to mean the published form. Rule 1.3 does not settle it, because the published format has two bit widths. Two providers are tagged fp4 on 2 October, so the lead does not depend on the answer
- Licence: MIT
- Census 2 Oct: 30 providers, 33 endpoints. By provider: fp8 15, unknown 13, fp4 2, fp32 1 (BaseTen, also listed at fp8). **Qualifying: 15**
- Watch: the head commit adds a chat template file with no change to weights. A template change is material under the methodology, so the hash to pin is the head, not the weights commit. An earlier commit, `dba1be0`, changed prompt encoding for tool namespaces
- Paper: listed on Hugging Face as arXiv 2609.19969, "DeepSeek-V4.1-Flash: Pushing the Limits of KV Cache Compression". Not read
- Correction: this entry previously said the model was first seen between 14 and 17 September. It is in the census from 11 September, the first census day, at 6 qualifying providers. The repository dates from about 10 September

### 3.5 deepseek-ai/DeepSeek-V4.1-Flash-1017

Placed on 17 October 2026, the day of release, as a Standard candidate under the watchlist rule in 1.7 (D3), and added to the probe as a third checkpoint so that its shadow windows build up from the day providers list it at an accepted precision. Collected from the Hugging Face model page, its `config.json`, the Hugging Face API and OpenRouter's listing.

- OpenRouter id: `deepseek/deepseek-v4.1-flash-1017`. Listed on OpenRouter about 08:27 UTC on 17 October, after that day's census; first census day 18 October. OpenRouter's alias `deepseek-flash-latest` points to it
- Commit hash: `1bae0e1088993b9b82de08f59de5be5a34e42170`, the head on 17 October, read through the Hugging Face API. Repository created 02:40 UTC, last modified 05:46 UTC. Confirm by hand from Files and versions before it is used as a reference identifier
- Described by DeepSeek as "a minor update to DeepSeek-V4.1-Flash", with higher scores on every listed benchmark and shorter replies
- Parameters: 763,205,315,794 in the Safetensors box, the same total as the reference. Active parameters are not stated on the card; the architecture is identical to the reference's, which states 8B during prefill and 16B during decode. **Standard** on either figure
- Architecture, from `config.json`: `deepseek_v41`, 40 layers, hidden 5120, 384 routed experts, 6 per token, 1 shared, vision tower of 32 layers. The same as the reference
- **Native precision: fp8 with fp4 experts,** as the reference: `quantization_config` gives quant_method "fp8", expert_dtype "fp4", weight_block_size 32 by 32, scale_fmt "ue8m0", activation_scheme "dynamic". Tensor types BF16, F32, F8_E4M3, I8
- **Accepted tag: fp8, provisional,** on the same reasoning as the reference (3.4)
- Prompt encoding: no Jinja chat template file. An `encoding/` folder holds a Python reference implementation with tests, and the card points production users to DeepSeek's own encoding library. A change to these files would be material under Rule 5, as a template change is
- Licence: MIT
- OpenRouter, 17 October: one endpoint, DeepSeek's own, precision "unknown", so **qualifying: 0**. Base price $0.15 input and $0.60 output per million, doubled on weekdays from 01:00 to 04:00 and 06:00 to 10:00 UTC. Reasoning optional, not mandatory, so eligible under rule 1.8 on that day's listing
- Why it matters: if it holds more qualifying providers than the reference on any census day, the reference's 20-day run under 1.4 ends; if it leads for 20 consecutive census days, it becomes the reference on the twentieth day under 1.6

---

## 4. Heavy grade candidates

### 4.1 zai-org/GLM-5.3

- OpenRouter id: `z-ai/glm-5.3`
- Commit hash: `aca966e4e02791568aa6a4ced368624b3d897f42`
- Parameters: 753B total (Safetensors), 40B active (GLM-5 announcement: GLM-5 scales from 355B/32B active to 744B/40B active)
- Discrepancy: card shows 753B total against 744B announced. Presumably a later revision within the series. Record both
- Native precision: **fp8**, per card tag. Tensor types BF16, F8_E4M3, F32
- Licence: `glm-5.3` custom, not MIT. Read before relying on it; restrictive terms could limit panel growth
- Census 17 Sep: 29 providers, 33 endpoints. fp8 15, unknown 10, fp4 7, nvfp4 1. **Qualifying: 13**
- Note: same base model as GLM-5.2; gains from post-training only

### 4.2 deepseek-ai/DeepSeek-V4-Pro-0813

- OpenRouter id: `deepseek/deepseek-v4-pro-0813`
- Commit hash: `72e1d3230f6c080a530b0a1d46f8eb4602340597`
- Parameters: 1.7T total (Safetensors, includes DSpark module), 1.6T main model, 49B active (technical report)
- Native precision: **fp8**, per card tags. Tensor types BF16, I64, F32, F8_E4M3, I8
- Licence: MIT
- Census 17 Sep: 20 providers, 22 endpoints. unknown 10, fp8 8, fp4 4. **Qualifying: 8**
- Alias warning: undated `deepseek/deepseek-v4-pro` is a separate listing with 15 providers

### 4.3 moonshotai/Kimi-K2.6

- OpenRouter id: `moonshotai/kimi-k2.6`
- Commit hash: `7eb5002f6aadc958aed6a9177b7ed26bb94011bb`
- Parameters: 1T total, 32B active (Model Summary table)
- Architecture: MoE, 384 routed experts, 8 per token, 1 shared, 61 layers.
  Context 262,144. Vision encoder 27 layers
- **Native precision: int4.** config.json quantization_config gives type
  "int", num_bits 4, format "pack-quantized", group_size 32, symmetric. Base
  dtype bfloat16
- Unquantised per the ignore list: self-attention, shared experts, dense MLP
  projections, lm_head, vision tower, mm projector
- **Accepted tag: int4 only.** Endpoints tagged fp4 are serving a form the lab
  did not publish, and are excluded under rule 1.3
- Licence: modified-mit. Read it
- Architecture note: the text config declares `DeepseekV3ForCausalLM` and ships
  DeepSeek's modelling files. K3, three weeks later, uses Moonshot's own
  `KimiLinearForCausalLM` with Kimi Delta Attention. A genuine generational
  break, and the likely reason the two panels differ so much: providers had
  DeepSeek V3 tooling ready for K2.6 and needed new work for K3
- Outstanding: config.json commit `2755962`, "support-transformers-inference",
  was made after release. Check whether it touched weights or only loading
  code. Weights change triggers rollover; loading code does not
- Grade: Heavy at 32B active, 7 per cent above the boundary, inside the 20 per
  cent review trigger

---

## 5. Frontier grade, under observation

### 5.1 moonshotai/Kimi-K3

- OpenRouter id: `moonshotai/kimi-k3`
- Commit hash: `c5d1dd4c428bd1ce8b88c5044f3b6ccde9e3b721` (config.json, initial commit)
- Parameters: 2.8T total, 104B active (technical report abstract, arXiv)
- Architecture: 896 routed experts, 16 per token, 2 shared, 93 layers, hidden
  7168. Context 1,048,576. Kimi Delta Attention on most layers with full
  attention every fourth. Native vision encoder, 27 layers
- **Native precision: mxfp4.** config.json gives format
  "mxfp4-pack-quantized", type "float", num_bits 4, group_size 32, symmetric.
  Base dtype bfloat16. Routed experts only
- Unquantised per the ignore list: self-attention, shared experts, dense MLP
  projections, lm_head, vision tower, mm projector
- **Accepted tags: mxfp4, fp4**, under rule 1.3
- Licence: kimi-k3 custom. Read it
- The "8-bit precision" page tag is wrong; config.json governs
- Closed premium evidence: the K3 report concedes K3 trails Claude Fable 5 and
  GPT-5.6 Sol while outperforming other open and proprietary models. The market
  prices that gap at roughly 3.3 times, $15 against $50

### 5.2 qwen/qwen3.8-2.4t-a95b

- Census 17 Sep: 7 providers, 7 endpoints. unknown 5, fp8 1, fp4 1. **Largest single-precision group: 1**
- All three price points identical at $6.00, which is unusual and worth understanding before this model is ever used

---

## 6. Closed models, for the premium series only

Nine Anthropic models appear at exactly five providers each with every endpoint marked unknown. One seller reselling through five channels, not five sellers. Never entered into an assessment; recorded as list prices for the closed premium series.

17 September: Opus family $25.00, high $27.50. Fable 5 $50.00, high $55.00. Sonnet family present. Against Kimi K3 at a $15.00 median, the closed frontier carries roughly a 67 per cent premium over the open frontier. Against the Standard band at around $0.50, the ratio is fifty to one.

---

## 7. Precision vocabulary observed

Maintained because the taxonomy is growing, which makes the declaration requirement harder for providers to satisfy and more valuable when they meet it.

| Tag | Meaning | Notes |
|---|---|---|
| `bf16` | 16-bit brain float | Native for older dense models; an upconversion for models published at lower precision |
| `fp16` | 16-bit float | Rare |
| `fp8` | 8-bit float | Native for GLM-5 series and DeepSeek V4 series |
| `mxfp4` | Microscaling 4-bit | Native for gpt-oss |
| `nvfp4` | Nvidia 4-bit, Blackwell | New; first seen on GLM models this week |
| `fp4` | 4-bit float, unspecified variant | Ambiguous; may or may not equal mxfp4 or nvfp4 |
| `int4` | 4-bit integer | Seen on Kimi |
| `unknown` | Not declared | Excluded under the methodology |

The ambiguity of bare `fp4` is a live problem for gpt-oss, whose native format is mxfp4. Decide before launch whether `fp4` on that model counts as native or is excluded, and write the decision into the methodology.

---

## 8. Open items

1. Settled 15 October: the DeepSeek V4.1-Flash commit hash, `5254448`
   (section 3.4). The fp4 question is settled by D5 (rule 1.7)
2. Settled 14 October: the larger active figure governs (D5, rule 1.7)
3. Settled 14 October: the amended launch threshold (D3, rule 1.7)
4. Resolve whether the Qwen 27B models are dense; if so, record the soft-edge
   finding properly
5. Read the GLM-5.3, Kimi K2.6 and Kimi K3 licences
6. Check whether Kimi K2.6 config commit `2755962` touched weights
7. Reconcile the DeepSeek V4 Flash 167 GB against 304B parameters. Its
   `config.json` has no key that explains it (section 3.2)
8. Check the Minimax M3 card; 8 fp8 providers and never examined
9. Add to the methodology: the once-per-day census rule (1.5), the launch
   threshold and maintenance floor (1.4), and reference selection before first
   publication (1.6); done in methodology 0.9, 20 October
10. Before methodology 1.0: whether a provider's lower-priority tier, such as
    DeepInfra's "flex", is the same product; whether the venue request should
    also carry the model maker's own switch for thinking; whether the test piece
    needs protecting against caching that ignores the unique first line. The
    promised cryptographic timestamp was built on 21 October (rule 1.13)

---

## 9. GPU-hour futures

Read 20 October 2026 (roadmap step 24), from CME's notice SER 9785 of
11 August 2026, the exchange's filing with the CFTC (rulebook chapters 1045
and 1047), and CME's settlements page.

- **Contracts.** Silicon Data H100 Rental Index Futures (CME Globex code GPU1)
  and Silicon Data B200 Rental Index Futures (GPU2), listed by NYMEX, trading
  since 5 October 2026, monthly contracts listed 36 months ahead
- **Underlying.** Silicon Data's daily on-demand rental index for each chip
- **Unit.** 730 GPU-hours per contract; quoted in US dollars per GPU-hour;
  minimum price step $0.01, which is $7.30 per contract
- **Settlement.** Cash, against the arithmetic average of the daily index over
  every business day of the contract month. Trading ends on the month's last
  business day
- **Settlements, H100, trade date 19 October 2026** (CME, last updated
  19 October, 23:55 Central time): November 2026 $2.810, December 2026 $2.760,
  January 2027 $2.730, February 2027 $2.740, March 2027 $2.750 per GPU-hour.
  Estimated volume 0; prior day open interest 0. The October 2026 contract was
  not shown
- **Reading.** Two weeks after launch nobody had traded the contracts; the
  settlement prices followed the index. The curve slopes down into January,
  which bears on break-even throughput in the derived series: a lower rental
  rate lowers it even if the token price does not move
