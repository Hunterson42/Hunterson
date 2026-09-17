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

### 1.2 Frontier grade defined but not published

No open-weight model in the frontier band reaches five distinct providers at a single declared precision.

- Kimi K3, 17 September: 17 providers, split unknown 9, fp4 4, fp8 3, mxfp4 3, bf16 1. Largest single-precision group: 4.
- Qwen 3.8 2.4T-A95B, 17 September: 7 providers, of which fp8 1 and fp4 1.

The cause is fragmentation, not scarcity: the largest models are the ones providers most need to shrink, and they shrink them differently. Waiting for more providers does not fix it.

Frontier is therefore defined in the methodology and marked under observation, publishable when five providers serve one checkpoint at a common declared precision.

---

## 2. Daily tracking

Generated automatically into `data/track.md` by `scripts/track.py`. That file rebuilds the full history from the saved census on every run and computes the 20-day stickiness streak for each challenger. Read it rather than transcribing counts by hand.

Manual snapshot for the record:

| Date | GLM-5.3-Flash fp8 | DS V4-Flash-0731 fp8 | DS V4.1-Flash fp8 | gpt-oss-120b mxfp4 |
|---|---|---|---|---|
| 14 Sep | 16 | 13 | not listed | 6 |
| 17 Sep | 15 | 12 | 9 | 6 |

Reading: GLM-5.3-Flash is strengthening while DeepSeek V4 Flash 0731 is flat. DeepSeek V4.1-Flash appeared between the two dates and reached 9 within days, which is the pattern the stickiness rule exists to absorb.

---

## 3. Standard grade candidates

### 3.1 zai-org/GLM-5.3-Flash

- OpenRouter id: `z-ai/glm-5.3-flash`
- Commit hash: `eb9eb208eb0d988989d07a6a12d0fdeb5f52574a`
- Parameters: 321B total (Safetensors), 18B active (model card)
- Native precision: **fp8**. Tensor types F8_E4M3 bulk, with BF16 and F32 components. Card tag: fp8
- Licence: MIT
- Census 17 Sep: 29 providers, 30 endpoints. fp8 18, unknown 8, fp4 3, nvfp4 1. **Qualifying: 18**
- Hugging Face serving partners: Zai, Together, Novita, Fireworks, DeepInfra, Baseten
- Watch: chat template changed at commit `690b705` after release. Template changes are material under the methodology; weight changes have not occurred

### 3.2 deepseek-ai/DeepSeek-V4-Flash-0731

- OpenRouter id: `deepseek/deepseek-v4-flash-0731`
- Commit hash: `7872f01b1d1fe23eabc4c98b48bffcef5a386062`
- Parameters: 304B total (Safetensors, includes DSpark speculative decoding module), 284B main model (technical report), 13B active (technical report, arXiv:2606.19348 abstract)
- Report caveat: the report describes the April preview; the 0731 card states the same structure plus the DSpark module
- Native precision: **fp8**, per card tags. Tensor types BF16, I64, F32, F8_E4M3, I8
- Licence: MIT
- Census 17 Sep: 27 providers, 29 endpoints. fp8 13, unknown 9, fp4 6, bf16 1. **Qualifying: 13**
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
- Census 17 Sep: 29 providers, 33 endpoints. fp8 15, unknown 10, fp4 7, nvfp4 1. **Qualifying: 15**
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
- Architecture: MoE, 384 experts, 8 selected per token, 1 shared, 61 layers. MoonViT vision encoder at 400M. Context 256K
- Native precision: **UNRESOLVED**. Tensor types F32, I32, BF16. The `compressed-tensors` tag names a quantisation framework, not a precision. Check `config.json` for the quantisation block
- Licence: modified-mit. Read it
- Census 17 Sep: 20 providers, 21 endpoints. int4 6, fp4 6, unknown 5, fp8 3, bf16 1. Most fragmented panel of any candidate. **Qualifying: at most 6, precision undetermined**
- Grade: Heavy at 32B active, 7 per cent above the boundary, inside the 20 per cent review trigger
- Not selectable as a reference until precision is resolved

---

## 5. Frontier grade, under observation

### 5.1 moonshotai/kimi-k3

- Census 17 Sep: 17 providers, 20 endpoints. unknown 9, fp4 4, fp8 3, mxfp4 3, bf16 1. **Largest single-precision group: 4**
- Median posted output: $15.00, range $10.95 to $22.50

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

1. Collect the model card for DeepSeek V4.1-Flash: hash, total and active parameters, native precision
2. Resolve Kimi K2.6 native precision from `config.json`
3. Resolve whether the Qwen 27B models are dense; if so, record the soft-edge finding properly
4. Read the GLM-5.3 and Kimi licences
5. Decide whether bare `fp4` counts as native for gpt-oss
6. Reconcile the DeepSeek V4 Flash 167 GB against 304B parameters
7. Choose the Standard reference and record the ten daily qualifying counts
8. Confirm the Heavy reference, on current data GLM-5.3 at 15 qualifying
