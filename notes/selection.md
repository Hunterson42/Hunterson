# Reference selection record

Working record for choosing and monitoring the reference checkpoint for each grade. Kept in the repository so that every selection decision has a dated, public trail. Nothing here is published; the methodology is the published document.

Last updated: 17 September 2026.

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

### 3.4 deepseek/deepseek-v4.1-flash

- OpenRouter id: `deepseek/deepseek-v4.1-flash`
- Commit hash: [to collect]
- Parameters: [to collect]
- Native precision: fp8 assumed from the census; confirm from the card
- Census 17 Sep: 18 providers, 19 endpoints. fp8 9, unknown 8, fp4 2. **Qualifying: 9**
- Status: new entrant, first seen between 14 and 17 September. Live rollover candidate. Collect the card before 25 September

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

## 8. Open items before 25 September

1. Collect the model card for DeepSeek V4.1-Flash: hash, total and active
   parameters, native precision
2. Resolve whether the Qwen 27B models are dense; if so, record the soft-edge
   finding properly
3. Read the GLM-5.3, Kimi K2.6 and Kimi K3 licences
4. Check whether Kimi K2.6 config commit `2755962` touched weights
5. Reconcile the DeepSeek V4 Flash 167 GB against 304B parameters
6. Check the Minimax M3 card; 8 fp8 providers and never examined
7. Choose the Standard reference and record the ten daily qualifying counts
8. Confirm the Heavy reference, noting the GLM-5.2 instability in section 2
9. Add the once-per-day census rule to the methodology data sources section
10. Add the launch threshold and maintenance floor to the methodology
