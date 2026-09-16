# 说明：真实模型推理镜像需要 CUDA + torch，体积很大；
# 这里提供一个"接口层"镜像，配合宿主机或远程推理服务使用。
FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CV_HOST=0.0.0.0 \
    CV_PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libsndfile1 ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pyproject.toml ./

# 默认以 Mock 模式启动，接入真实模型时覆盖 CV_MOCK / CV_MODEL_DIR
ENV CV_MOCK=true
ENV CV_DATA_DIR=/data
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
