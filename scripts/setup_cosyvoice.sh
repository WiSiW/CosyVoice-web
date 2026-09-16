#!/usr/bin/env bash
# 拉取 CosyVoice 官方仓库（含 third_party 子模块）并下载默认模型权重。
#
# 用法:
#   bash scripts/setup_cosyvoice.sh                # 默认 CosyVoice2-0.5B
#   MODEL_ID=iic/CosyVoice-300M bash scripts/setup_cosyvoice.sh
#   MODEL_ID=FunAudioLLM/Fun-CosyVoice3-0.5B-2512 bash scripts/setup_cosyvoice.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COSYVOICE_DIR="${COSYVOICE_DIR:-${PROJECT_ROOT}/CosyVoice}"
MODEL_ID="${MODEL_ID:-iic/CosyVoice2-0.5B}"
PYTHON="${PYTHON:-python3}"

echo "==> 项目根目录 : ${PROJECT_ROOT}"
echo "==> CosyVoice   : ${COSYVOICE_DIR}"
echo "==> 目标模型    : ${MODEL_ID}"

if [[ -d "${COSYVOICE_DIR}/.git" ]]; then
  echo "==> CosyVoice 仓库已存在，执行 git pull"
  git -C "${COSYVOICE_DIR}" pull --ff-only
else
  echo "==> 克隆 CosyVoice 官方仓库"
  git clone --recursive https://github.com/QwenAudio/CosyVoice.git "${COSYVOICE_DIR}"
fi

echo "==> 同步子模块 (third_party/Matcha-TTS 为推理必需依赖)"
git -C "${COSYVOICE_DIR}" submodule update --init --recursive

echo "==> 安装 CosyVoice 运行依赖"
if [[ -x "${PROJECT_ROOT}/backend/.venv/bin/pip" ]]; then
  PIP="${PROJECT_ROOT}/backend/.venv/bin/pip"
else
  PIP="${PYTHON} -m pip"
fi
# shellcheck disable=SC2086
${PIP} install -r "${COSYVOICE_DIR}/requirements.txt"

echo "==> 下载模型权重: ${MODEL_ID}"
TARGET_DIR="${COSYVOICE_DIR}/pretrained_models/$(basename "${MODEL_ID}")"
"${PYTHON}" - <<PY
from modelscope import snapshot_download
path = snapshot_download("${MODEL_ID}", local_dir="${TARGET_DIR}")
print("模型已下载到:", path)
PY

cat <<MSG

============================================================
完成。请在 backend/.env 中配置:

  CV_COSYVOICE_REPO=${COSYVOICE_DIR}
  CV_MODEL_DIR=${TARGET_DIR}

然后启动后端:
  make api
============================================================
MSG
