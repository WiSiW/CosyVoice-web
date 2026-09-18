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

echo "==> 安装 CosyVoice 推理依赖（自动处理平台差异）"
# 说明：不要直接 pip install -r CosyVoice/requirements.txt
#   * openai-whisper 只有 sdist，新版 setuptools 移除了 pkg_resources，会构建失败
#   * Intel Mac 上 torch==2.3.1 没有轮子（最后可用版本为 2.2.2）
# scripts/install_cosyvoice_deps.sh 已处理以上问题。
bash "${PROJECT_ROOT}/scripts/install_cosyvoice_deps.sh"

echo "==> 下载模型权重: ${MODEL_ID}"
TARGET_DIR="${COSYVOICE_DIR}/pretrained_models/$(basename "${MODEL_ID}")"
"${PYTHON}" - <<PY
from pathlib import Path
from modelscope import snapshot_download
path = Path(snapshot_download("${MODEL_ID}", local_dir="${TARGET_DIR}"))
print("模型已下载到:", path)

yaml_files = list(path.glob("cosyvoice*.yaml"))
if not yaml_files:
    raise SystemExit(f"[错误] {path} 下没有 cosyvoice*.yaml，权重可能不完整，请重新下载")
missing = [name for name in ("llm.pt", "flow.pt", "hift.pt") if not (path / name).exists()]
if missing:
    raise SystemExit(f"[错误] 模型文件缺失: {', '.join(missing)}，请重新下载")
print("权重校验通过:", ", ".join(f.name for f in yaml_files))
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
