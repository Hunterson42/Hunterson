# Candidate tracking, rebuilt 2026-09-17 12:03 UTC

Qualifying providers = distinct providers serving the checkpoint at its native precision.
Bracketed figure is the total provider count at any precision, for context.

## Standard (30B active or fewer)

| Model | Native | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 | 09-16 | 09-17 |
|---|---|---|---|---|---|---|---|---|
| z-ai/glm-5.3-flash *(reference)* | fp8 | **14** (25) | **15** (26) | **15** (26) | **16** (28) | **16** (27) | **15** (26) | **15** (27) |
| deepseek/deepseek-v4-flash-0731 | fp8 | **11** (27) | **11** (27) | **11** (27) | **12** (27) | **11** (26) | **12** (27) | **12** (27) |
| deepseek/deepseek-v4.1-flash | fp8 | **6** (9) | **8** (12) | **8** (13) | **9** (16) | **8** (17) | **9** (18) | **8** (18) |
| openai/gpt-oss-120b | mxfp4 or fp4 | **5** (19) | **5** (19) | **5** (19) | **5** (19) | **5** (20) | **5** (20) | **5** (20) |
| qwen/qwen3.6-35b-a3b | fp8 | **8** (11) | **8** (11) | **8** (11) | **8** (11) | **8** (11) | **8** (11) | **8** (10) |
| google/gemma-4-26b-a4b-it | bf16 | **5** (11) | **5** (11) | **5** (11) | **5** (11) | **5** (11) | **5** (11) | **5** (11) |

### Stickiness against z-ai/glm-5.3-flash

- deepseek/deepseek-v4-flash-0731: not leading
- deepseek/deepseek-v4.1-flash: not leading
- openai/gpt-oss-120b: not leading
- qwen/qwen3.6-35b-a3b: not leading
- google/gemma-4-26b-a4b-it: not leading

## Heavy (above 30B active)

| Model | Native | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 | 09-16 | 09-17 |
|---|---|---|---|---|---|---|---|---|
| z-ai/glm-5.3 *(reference)* | fp8 | **13** (27) | **11** (25) | **11** (25) | **12** (26) | **13** (27) | **13** (28) | **13** (29) |
| z-ai/glm-5.2 | fp8 | **13** (24) | **13** (24) | **13** (24) | **12** (23) | **12** (23) | **12** (23) | **12** (23) |
| deepseek/deepseek-v4-pro-0813 | fp8 | **8** (19) | **8** (20) | **8** (20) | **8** (20) | **8** (20) | **8** (20) | **8** (20) |
| moonshotai/kimi-k2.6 | UNRESOLVED | **0** (20) | **0** (20) | **0** (20) | **0** (20) | **0** (20) | **0** (20) | **0** (20) |

### Stickiness against z-ai/glm-5.3

- z-ai/glm-5.2: not leading
- deepseek/deepseek-v4-pro-0813: not leading
- moonshotai/kimi-k2.6: not leading

## Frontier (not published)

| Model | Native | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 | 09-16 | 09-17 |
|---|---|---|---|---|---|---|---|---|
| moonshotai/kimi-k3 | UNRESOLVED | **0** (16) | **0** (16) | **0** (17) | **0** (17) | **0** (17) | **0** (17) | **0** (17) |
| qwen/qwen3.8-2.4t-a95b | fp8 | **1** (7) | **1** (7) | **1** (7) | **1** (7) | **1** (7) | **1** (7) | **1** (7) |

## Soft edge, monitoring only

| Model | Native | 09-11 | 09-12 | 09-13 | 09-14 | 09-15 | 09-16 | 09-17 |
|---|---|---|---|---|---|---|---|---|
| qwen/qwen3.8-27b *(reference)* | fp8 | **9** (14) | **9** (14) | **9** (15) | **9** (15) | **9** (16) | **9** (16) | **9** (16) |
| qwen/qwen3.6-27b | fp8 | **4** (6) | **4** (6) | **4** (6) | **4** (6) | **4** (6) | **4** (6) | **4** (6) |

### Stickiness against qwen/qwen3.8-27b

- qwen/qwen3.6-27b: not leading

## Watchlist

Models seen in the census with five or more providers at a single declared
precision that are not listed above. Check whether they belong in a grade.

- z-ai/glm-5.1: 11 providers at fp8
- deepseek/deepseek-v4-flash: 11 providers at fp8
- deepseek/deepseek-v4-pro: 9 providers at fp8
- minimax/minimax-m3: 8 providers at fp8
- z-ai/glm-5: 7 providers at fp8
- deepseek/deepseek-v3.2: 7 providers at fp8
- qwen/qwen3.5-397b-a17b: 6 providers at unknown
- qwen/qwen3-235b-a22b-2507: 6 providers at fp8
- xiaomi/mimo-v2.5: 5 providers at fp8
- moonshotai/kimi-k2.7-code: 5 providers at int4
- minimax/minimax-m2.7: 5 providers at fp8
- google/gemma-4-31b-it: 5 providers at fp4
- deepseek/deepseek-chat-v3.1: 5 providers at fp8
