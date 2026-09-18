# ===========================================================================
# CosyVoice Web 后端镜像
#
#   仅 Web 服务层（默认，体积小）：
#     docker build -t cosyvoice-web .
#
#   连推理依赖一起装（体积大，构建时间长）：
#     docker build --build-arg INSTALL_INFERENCE_DEPS=true -t cosyvoice-web .
#
# 真实 GPU 推理请把基础镜像换成 CUDA 版本，例如
#   FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
# 并按 https://github.com/QwenAudio/CosyVoice 的说明安装 torch。
#
# 运行时必须提供模型权重与 CosyVoice 仓库：
#   -v /path/to/CosyVoice:/opt/CosyVoice:ro
#   -v /path/to/data:/data
# 否则后端会以 state=error 启动并给出明确原因（不会返回假音频）。
# ===========================================================================
FROM python:3.10-slim

ARG INSTALL_INFERENCE_DEPS=false

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CV_HOST=0.0.0.0 \
    CV_PORT=8000 \
    CV_DATA_DIR=/data \
    CV_COSYVOICE_REPO=/opt/CosyVoice

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-cosyvoice.txt build-constraints.txt ./

# 只用 -U 升级 pip；setuptools 必须留在 <81（lightning 2.2.4 运行期仍 import pkg_resources）
RUN pip install -U pip \
    && pip install "setuptools<81" wheel \
    && pip install -r requirements.txt

RUN if [ "$INSTALL_INFERENCE_DEPS" = "true" ]; then \
        pip install --build-constraint build-constraints.txt -r requirements-cosyvoice.txt; \
    fi

COPY app ./app
COPY pyproject.toml ./

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
