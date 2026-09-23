#!/usr/bin/env bash
# ===========================================================================
# 安装后端 + CosyVoice 推理依赖（自动处理平台差异）
#
#   bash scripts/install_cosyvoice_deps.sh
#
# 主要解决两个常见报错：
#   1. openai-whisper 构建失败: ModuleNotFoundError: No module named 'pkg_resources'
#      —— 新版 setuptools(>=81) 移除了 pkg_resources，而 whisper 的 setup.py 仍在用它。
#         这里通过约束"构建期"的 setuptools 版本解决。
#   2. Intel Mac 上 torch==2.3.1 找不到轮子
#      —— requirements-cosyvoice.txt 已按平台自动降级到 2.2.2。
# ===========================================================================
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${PROJECT_ROOT}/backend"
VENV_DIR="${VENV_DIR:-${BACKEND_DIR}/.venv}"
PYTHON="${PYTHON:-python3}"
PROJECT_ROOT_DISPLAY="${PROJECT_ROOT}"

if command -v cygpath >/dev/null 2>&1; then
  PROJECT_ROOT_DISPLAY="$(cygpath -m "${PROJECT_ROOT}")"
fi

cyan() { printf "\033[36m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }

# --------------------------------------------------------------- 1. 虚拟环境
# Windows / Git Bash 的 venv 使用 Scripts/python.exe；Linux / macOS 使用
# bin/python。优先复用已有环境，并兼容两种目录布局。
if [[ -x "${VENV_DIR}/bin/python" ]]; then
  PY="${VENV_DIR}/bin/python"
elif [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
  PY="${VENV_DIR}/Scripts/python.exe"
else
  cyan "==> 创建虚拟环境 ${VENV_DIR}"
  "${PYTHON}" -m venv "${VENV_DIR}"

  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    PY="${VENV_DIR}/bin/python"
  elif [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
    PY="${VENV_DIR}/Scripts/python.exe"
  else
    warn "无法找到虚拟环境中的 Python 可执行文件: ${VENV_DIR}"
    exit 1
  fi
fi
PIP=("${PY}" -m pip)

cyan "==> Python 版本: $(${PY} -V 2>&1)"
cyan "==> 平台: $(uname -s) / $(uname -m)"

# --------------------------------------------------------- 2. Web 服务层依赖
cyan "==> 安装 Web 服务层依赖 (backend/requirements.txt)"
# 只用 -U 升级 pip；setuptools 必须留在 <81：
#   * openai-whisper 的 setup.py 需要 pkg_resources（仅构建期）
#   * lightning 2.2.4 运行期也 import pkg_resources
# 盲目 `pip install -U setuptools` 会装到 81+ 并把 pkg_resources 移除，
# 导致后续出现难以定位的 ModuleNotFoundError。
"${PIP[@]}" install -U pip >/dev/null
"${PIP[@]}" install "setuptools<81" wheel
"${PIP[@]}" install -r "${BACKEND_DIR}/requirements.txt"

# ------------------------------------------------- 3. 构建期约束（核心修复点）
BUILD_CONSTRAINTS="${BACKEND_DIR}/build-constraints.txt"
cyan "==> 构建期约束: ${BUILD_CONSTRAINTS} (setuptools<81, wheel)"

# ------------------------------------------------- 4. 安装 CosyVoice 推理依赖
PIP_VERSION="$("${PIP[@]}" --version | awk '{print $2}')"
REQUIREMENTS="${BACKEND_DIR}/requirements-cosyvoice.txt"

# --build-constraint 需要 pip >= 25.1；旧版 pip 改用 --no-build-isolation 兜底
pip_supports_build_constraint() {
  # 若 25.1 是两者中较小的那个，说明当前 pip 版本 >= 25.1
  [ "$(printf '%s\n%s\n' "25.1" "${PIP_VERSION}" | sort -V | head -n1)" = "25.1" ]
}

if pip_supports_build_constraint; then
  cyan "==> pip ${PIP_VERSION} 支持 --build-constraint，开始安装推理依赖"
  "${PIP[@]}" install --build-constraint "${BUILD_CONSTRAINTS}" -r "${REQUIREMENTS}"
else
  warn "==> pip ${PIP_VERSION} 不支持 --build-constraint，改用 --no-build-isolation 兜底"
  warn "    （已有 setuptools<81 与 wheel，构建行为等价）"
  "${PIP[@]}" install --no-build-isolation -r "${REQUIREMENTS}"
fi

# ------------------------------------------------------------- 5. 安装校验
cyan "==> 校验导入"
"${PY}" - <<'CHECK'
import sys

import numpy
import onnxruntime
import soundfile
import torch
import torchaudio
import transformers
import whisper

print("python       ", sys.version.split()[0])
print("torch        ", torch.__version__, "| cuda:", torch.cuda.is_available())
print("torchaudio   ", torchaudio.__version__)
print("numpy        ", numpy.__version__)
print("soundfile    ", soundfile.__version__)
print("whisper      ", getattr(whisper, "__version__", "ok"))
print("onnxruntime  ", onnxruntime.__version__)
print("transformers ", transformers.__version__)
CHECK

cyan ""
cyan "============================================================"
cyan " 依赖安装完成"
cyan "============================================================"
echo "下一步："
echo "  1) 克隆官方仓库与权重（若尚未执行）"
echo "       bash scripts/setup_cosyvoice.sh"
echo "  2) 配置 backend/.env"
echo "       CV_COSYVOICE_REPO=${PROJECT_ROOT_DISPLAY}/CosyVoice"
echo "       CV_MODEL_DIR=${PROJECT_ROOT_DISPLAY}/CosyVoice/pretrained_models/CosyVoice2-0.5B"
echo "  3) 启动后端"
if [[ -x "${VENV_DIR}/Scripts/python.exe" ]]; then
  echo "       cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --port 8000"
else
  echo "       cd backend && .venv/bin/uvicorn app.main:app --port 8000"
fi
