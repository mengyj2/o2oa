#!/usr/bin/env bash
# ============================================================================
#  组装官方 llama.cpp standalone 运行目录（可重复执行）
#
#  背景：官方 llama.cpp Windows release（b11046/b11045）的 llama-server.exe
#  在本机直接运行会失败（0xC0E90002 SxS）。根因是官方包内的 ggml-base.dll /
#  ggml-hip.dll 的加载链与官方 exe 组合时激活上下文构建失败；而 LM Studio
#  （Bionic）随包的一套 DLL 可正常工作（同一版本 0.3.0-dev commit 0f3a71b）。
#
#  结论方案：用【官方 llama-server.exe】+【已验证可用的完整 DLL 集】组装，
#  实测 ROCm 加速正常（AMD Radeon 8060S，44 tok/s 生成）。
#  这样既拿到官方二进制，又绕开官方包的 DLL 缺陷。
#
#  用法: bash build_llama_standalone.sh [输出目录]
#  默认输出: /d/O2OA/llama.cpp/standalone
# ============================================================================
set -euo pipefail

OUT="${1:-/d/O2OA/llama.cpp/standalone}"

# 来源 1：LM Studio 的后端运行时（llama.cpp 2.33.0，ROCm）
LMSD="$HOME/.lmstudio/extensions/backends/llama.cpp-win-x86_64-amd-rocm-avx2-2.33.0"
# 来源 2：LM Studio 的 ROCm vendor 运行时（amdhip64/libhipblas/rocblas）
VEND="$HOME/.lmstudio/extensions/backends/vendor/win-llama-rocm-vendor-v6/bin"
# 来源 3：官方 llama.cpp release（提供 llama-server.exe）
OFFICIAL="${OFFICIAL:-/d/O2OA/llama.cpp/rocm}"

for d in "$LMSD" "$VEND" "$OFFICIAL"; do
  [ -d "$d" ] || { echo "[错误] 目录不存在: $d" >&2; exit 1; }
done

echo "[1/4] 准备输出目录 $OUT"
rm -rf "$OUT"; mkdir -p "$OUT"

echo "[2/4] 复制 LM Studio 后端运行时 (核心 DLL)"
cp "$LMSD"/*.dll "$OUT"/

echo "[3/4] 复制 ROCm vendor 运行时 (amdhip64/libhipblas/rocblas)"
cp "$VEND"/*.dll "$OUT"/ 2>/dev/null || true
[ -d "$VEND/rocblas" ] && cp -r "$VEND/rocblas" "$OUT"/

# ★ 关键：ggml-hip.dll 硬依赖名为 hipblas.dll，而 vendor 里叫 libhipblas.dll。
#   缺这一步 → 运行时报 0xC0000135 (DLL 缺失)。缺一不可，勿删。
if [ -f "$VEND/libhipblas.dll" ]; then
  cp "$VEND/libhipblas.dll" "$OUT/hipblas.dll"
  echo "      ↳ libhipblas.dll → hipblas.dll (满足 ggml-hip.dll 的硬依赖)"
elif [ ! -f "$OUT/hipblas.dll" ]; then
  echo "[错误] vendor 中既无 libhipblas.dll，输出目录也无 hipblas.dll" >&2
  exit 1
fi

echo "[4/4] 放入官方 llama-server.exe"
cp "$OFFICIAL/llama-server.exe" "$OUT"/

echo
echo "完成。目录内容（$(ls "$OUT" | wc -l) 项）："
ls "$OUT" | tr '\n' ' '; echo
echo
echo "验证:"
echo "  cd \"$OUT\" && ./llama-server.exe --list-devices"
