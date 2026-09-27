---
name: lmstudio-backend-install
agent_created: true
description: Install, list, select, and verify LM Studio / Bionic inference backends (llama.cpp ROCm / CUDA / Vulkan) via the bundled `lms` CLI. Use whenever the user wants to add, switch, or troubleshoot a model inference backend in LM Studio (Bionic).
category: integration

---

# LM Studio / Bionic Backend Install

Install and switch LM Studio (Bionic) inference backends through the bundled `lms` CLI instead of the GUI.

## When to use
- User wants to install/add/switch a backend: ROCm, CUDA, Vulkan, CPU, etc.
- "在 Bionic 装 ROCm 后端", "换 CUDA 后端", "llama.cpp backend", "模型加载后端"
- Troubleshooting model-load failures related to the inference engine.

## Key facts (verified 2026-08-28)
- `lms.exe` lives at `~/.lmstudio/bin/lms.exe` (Windows). In the Bash tool it is NOT on PATH; call with the full path.
- Backends are downloaded to `~/.lmstudio/extensions/backends/<name>-<version>/`.
- Bionic's active backend preference is `$HOME/.lmstudio/apps/bionic/.internal/backend-preferences-v1.json` — an array of `{model_format, name, version}`. `lms runtime select` updates this file automatically.
- `lms runtime ls` shows installed engines with `✓` on the selected one.

## Workflow
1. List available variants (no download): `"$HOME/.lmstudio/bin/lms.exe" runtime get --list "<query>"`
   - Query patterns: `llama.cpp:rocm` -> `llama.cpp-win-x86_64-amd-rocm-avx2`
   - `llama.cpp:cuda` -> `llama.cpp-win-x86_64-nvidia-cuda-avx2`
   - `llama.cpp` (no suffix) lists all llama.cpp variants
   - `llama.cpp@<version>` pins a version (e.g. `llama.cpp@2.29.1`)
2. Install: `"$HOME/.lmstudio/bin/lms.exe" runtime get "<query>" -y`
   - Downloads ~200-600 MB. Background it if slow: run via Bash `run_in_background` and poll the log (progress bar uses CR carriage returns; `tr '\r' '\n'` to read).
3. Select: `"$HOME/.lmstudio/bin/lms.exe" runtime select "<name>@<version>"`
4. Verify: `"$HOME/.lmstudio/bin/lms.exe" runtime ls` and re-read `backend-preferences-v1.json`.

## Pitfalls / notes
- `lms` is not on PATH inside the POSIX shell; always use the absolute path.
- ROCm backend on Windows ships its own HIP runtime (`ggml-hip.dll`, `llm_engine_rocm.node`) so it usually needs no separate AMD ROCm SDK.
- For large iGPU VRAM (AMD Strix Halo UMA, e.g. 395/96GB), even ROCm/Vulkan can hit Windows commit limits -> enlarge the page file (虚拟内存) to >=64 GB. The "页面文件太小" error in server logs is the telltale sign, independent of backend.
- If ROCm load still fails, confirm the AMD Adrenalin/ROCm driver exposes the GPU; `lms runtime survey` lists hardware the runtime sees.
