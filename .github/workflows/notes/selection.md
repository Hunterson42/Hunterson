Candidate: Standard reference
Repository: zai-org/GLM-5.3-Flash
Commit hash: eb9eb208eb0d988989d07a6a12d0fdeb5f52574a
Total parameters: 321B (Safetensors); active 18B (model card)
Published precision: fp8 (F8_E4M3 bulk, BF16 and F32 components); tag fp8
Licence: MIT
Census 2026-09-14: 28 providers, of which 16 declare fp8, 9 undeclared, 3 fp4
Qualifying at native precision: 16
HF Inference Providers listed: Zai, Together, Novita, Fireworks, DeepInfra, Baseten

Candidate: Standard reference
Repository: deepseek-ai/DeepSeek-V4-Flash-0731
Commit hash: 7872f01b1d1fe23eabc4c98b48bffcef5a386062
Total parameters: 304B (Safetensors box, includes speculative decoding module); 284B main model (technical report)
Active parameters: 13B (technical report, arXiv:2606.19348, abstract)
Report caveat: report describes the April preview; 0731 card states same structure plus DSpark speculative decoding module
Published tensor types: BF16, I64, F32, F8_E4M3, I8
Published precision: fp8, per model card tags
Licence: MIT
Census 2026-09-14: 27 providers; 13 fp8, 9 undeclared, 5 fp4, 1 bf16
Qualifying at native precision: 13
HF Inference Providers listed: Together, Novita, Fireworks, DeepInfra, Baseten, Scaleway
Release: 0731 supersedes the preview; undated "deepseek-v4-flash" on OpenRouter is a separate alias with 17 providers
Heavy-band reference point: DeepSeek-V4-Pro 1.6T total, 49B active (same report)

Candidate: Standard reference
Repository: openai/gpt-oss-120b
Commit hash: b5c939de8f754692c1647ca79fbf85e8c1e70f8a
Total parameters: 117B (model card and Safetensors box agree)
Active parameters: 5.1B (model card)
Published tensor types: BF16, U8
Published precision: mxfp4, per model card tag. NOT fp8.
  MoE expert weights are 4-bit (mxfp4, stored as U8); remaining layers BF16.
  Designed to fit a single 80GB GPU (H100 or MI300X) in this form.
Licence: Apache 2.0
Census 2026-09-14: 19 providers, 23 endpoints; 9 undeclared, 6 fp4, 4 bf16, 3 fp8, 1 fp16
Qualifying at native precision (fp4/mxfp4): 6
HF Inference Providers listed: Together AI, Scaleway, OVHcloud AI Endpoints,
  Nscale, Novita, Groq, Fireworks, Featherless AI, DeepInfra, Cerebras, Baseten
Sibling: gpt-oss-20b, 21B total, 3.6B active

HEAVY GRADE CANDIDATES

deepseek-ai/DeepSeek-V4-Pro-0813
  Commit hash: 72e1d3230f6c080a530b0a1d46f8eb4602340597
  Total: 1.7T (Safetensors, incl. DSpark module); 1.6T main model (tech report)
  Active: 49B (tech report, arXiv:2606.19348 abstract)
  Tensor types: BF16, I64, F32, F8_E4M3, I8
  Precision: fp8, per card tags (fp8 and 8-bit precision)
  Licence: MIT
  Census 14 Sep: 20 providers; 10 undeclared, 8 fp8, 3 fp4. Qualifying fp8: 8
  HF partners: Together, Novita, Fireworks, DeepInfra, Baseten
  Note: 0813 supersedes the preview; same structure plus DSpark module

zai-org/GLM-5.3
  Commit hash: aca966e4e02791568aa6a4ced368624b3d897f42
  Total: 753B (Safetensors)
  Active: 40B
  Tensor types: BF16, F8_E4M3, F32
  Precision: fp8, per card tag
  Licence: glm-5.3 (custom, NOT MIT). Read it before including; a restrictive
    licence could stop providers serving it and shrink the panel
  Census 14 Sep: 26 providers, 27 endpoints; 12 fp8, 9 undeclared, 6 fp4.
    Qualifying fp8: 12
  HF partners: Zai, Together, Novita, Fireworks, DeepInfra, Baseten
  Note: same base model as GLM-5.2, gains from post-training only

moonshotai/Kimi-K2.6
  Commit hash: 7eb5002f6aadc958aed6a9177b7ed26bb94011bb
  Total: 1T. Active: 32B (Model Summary table)
  Architecture: MoE, 384 experts, 8 selected per token, 1 shared, 61 layers
  Multimodal: MoonViT vision encoder, 400M params. Context 256K
  Tensor types: F32, I32, BF16. Tag "compressed-tensors" is a framework,
    not a precision. Native precision UNRESOLVED; check config.json
  Licence: modified-mit. Read it
  Census 14 Sep: 20 providers, 21 endpoints; 6 fp4, 6 int4, 5 undeclared,
    3 fp8, 1 bf16. Most fragmented panel of any candidate
  HF partners: Novita, Fireworks, Featherless, DeepInfra, Baseten
  Grade: Heavy at 32B active, 7% above the 30B boundary. Inside the 20%
    review trigger; review recorded at launch
