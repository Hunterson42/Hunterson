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
