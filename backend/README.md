# CosyVoice Web Backend

基于 FastAPI 的语音合成服务，封装 [CosyVoice](https://github.com/QwenAudio/CosyVoice) 官方推理接口。

完整项目说明见仓库根目录 `README.md`。

## 启动

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Web 层依赖
.venv/bin/pip install -r ../CosyVoice/requirements.txt   # 真实推理依赖（可选）

cp .env.example .env

# Mock 模式（无 GPU / 无权重）
CV_MOCK=true .venv/bin/uvicorn app.main:app --reload --port 8000

# 真实模型
.venv/bin/uvicorn app.main:app --port 8000
```

也可以直接使用内置 CLI：

```bash
python -m app.main --mock --port 8000
python -m app.main --model-dir ../CosyVoice/pretrained_models/CosyVoice2-0.5B --preload
python -m app.main --repo /path/to/CosyVoice --model-dir iic/CosyVoice2-0.5B
```

## 分层结构

| 层 | 位置 | 职责 |
| --- | --- | --- |
| 路由层 | `app/api/` | 参数解析、依赖注入、HTTP 语义（状态码/响应头/流式） |
| 服务层 | `app/services/` | 业务校验、模式分发、结果落盘、音色库管理 |
| 核心层 | `app/core/` | 模型生命周期、CosyVoice 封装、Mock 后端、异常定义 |
| 工具层 | `app/utils/` | WAV 读写、音频校验（仅依赖标准库 + numpy + soundfile） |

设计要点：

* **模型懒加载 + 单例**：`ModelManager` 保证同一进程只持有一份模型，并用信号量串行化
  推理调用（上游 `model.tts` 非线程安全）。
* **前后端契约单一来源**：`app/services/modes.py` 定义了每种合成模式需要哪些表单字段，
  前端通过 `GET /api/v1/system/modes` 动态渲染表单，避免字段漂移。
* **优雅降级**：`CV_MOCK=true` 或真实模型加载失败时自动切换到 `MockBackend`，
  接口行为与真实后端一致（同样的分片节奏、采样率头、落盘逻辑）。

## 环境变量

见 `.env.example`，所有变量以 `CV_` 为前缀。常用项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CV_MODEL_DIR` | `iic/CosyVoice2-0.5B` | 本地目录或 ModelScope repo id |
| `CV_COSYVOICE_REPO` | `../CosyVoice` | 官方仓库路径（含 `third_party/Matcha-TTS`） |
| `CV_MOCK` | `false` | Mock 后端 |
| `CV_PRELOAD_MODEL` | `false` | 启动即加载模型 |
| `CV_FP16` / `CV_LOAD_JIT` / `CV_LOAD_TRT` / `CV_LOAD_VLLM` | `false` | 加速开关 |
| `CV_API_PREFIX` | `/api/v1` | 接口前缀 |
| `CV_CORS_ORIGINS` | `["http://localhost:5173"]` | 允许跨域的前端地址 |
| `CV_DATA_DIR` | `../data` | 数据目录（音色库 / 生成结果 / 临时文件） |

## 数据目录

```
data/
├── voices/<voice_id>/meta.json    # 音色元数据
├── voices/<voice_id>/prompt.wav   # 参考音频
├── outputs/<时间戳>_<id>.wav       # 生成结果（超过 CV_MAX_HISTORY_FILES 自动清理）
└── tmp/                            # 请求期间的临时上传文件，请求结束即删除
```

## 测试

```bash
.venv/bin/python -m pytest -q
```

测试全部基于 Mock 后端，覆盖：音频工具、音色 CRUD、参数校验、一次性合成、流式合成、
历史记录与错误码，无需 GPU 与模型权重。

## Docker

```bash
docker build -t cosyvoice-web-backend .
docker run --rm -p 8000:8000 -v $PWD/../data:/data cosyvoice-web-backend
```

镜像默认以 `CV_MOCK=true` 启动（接口层镜像）。接入真实模型时请基于 CUDA 基础镜像，
并挂载 CosyVoice 仓库与权重目录。
