# CosyVoice Web Backend

基于 FastAPI 的语音合成服务，封装 [CosyVoice](https://github.com/QwenAudio/CosyVoice) 官方推理接口。

完整项目说明见仓库根目录 `README.md`。

## 启动

```bash
# 推荐：一条命令装齐 Web 层 + CosyVoice 推理依赖（自动处理平台差异）
bash ../scripts/install_cosyvoice_deps.sh          # 等价于在根目录执行 make deps

# 或者手动分两步
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt          # 仅 Web 服务层
.venv/bin/pip install --build-constraint build-constraints.txt \
    -r requirements-cosyvoice.txt                  # CosyVoice 推理依赖

cp .env.example .env
.venv/bin/uvicorn app.main:app --port 8000
```

也可以直接使用内置 CLI：

```bash
python -m app.main --model-dir ../CosyVoice/pretrained_models/CosyVoice2-0.5B --preload
python -m app.main --repo /path/to/CosyVoice --model-dir iic/CosyVoice2-0.5B
```

> 本服务**没有模拟推理模式**：模型不可用时 `POST /api/v1/system/load` 与所有合成接口
> 都会返回明确错误（`state=error` + 原因），不会产出"不是人声的音频"。

## 依赖说明

| 文件 / 脚本 | 用途 |
| --- | --- |
| `requirements.txt` | 仅 Web 服务层（FastAPI、pydantic、numpy、soundfile、pytest） |
| `requirements-cosyvoice.txt` | CosyVoice 推理依赖，由官方 `CosyVoice/requirements.txt` 裁剪而来 |
| `scripts/install_cosyvoice_deps.sh` | 一键安装上面两者，并处理平台差异 |
| `build-constraints.txt` | 构建隔离环境的约束（setuptools<81），供 pip `--build-constraint` 使用 |

不要直接执行 `pip install -r ../CosyVoice/requirements.txt`，在 macOS 上会失败：

* **`openai-whisper` 构建报错** `ModuleNotFoundError: No module named 'pkg_resources'`
  —— setuptools ≥ 81 移除了 `pkg_resources`，而 whisper 只有 sdist 必须现场构建。
  需要给**构建隔离环境**加约束：`pip install --build-constraint <(echo "setuptools<81") ...`。
  注意 `PIP_CONSTRAINT` 环境变量对构建隔离不生效。
* **`torch==2.3.1` 在 Intel Mac 上无轮子** —— 2.2.2 是最后一个支持 macOS x86_64 的版本，
  `requirements-cosyvoice.txt` 已用环境标记自动选择。
* **`pyworld` 编译失败** —— 需要本机 C/C++ 编译器（macOS 装 Xcode Command Line Tools 即可）；
  它虽是训练链路文件里的 import，但 `cosyvoice2.yaml` 会被急切解析，因此推理也必需。
  `deepspeed` 则是真正的训练专用依赖，已移除。

`cosyvoice/tokenizer/tokenizer.py` 在推理时会 `import whisper.tokenizer`，因此 whisper
不能省略。

## 分层结构

| 层 | 位置 | 职责 |
| --- | --- | --- |
| 路由层 | `app/api/` | 参数解析、依赖注入、HTTP 语义（状态码/响应头/流式） |
| 服务层 | `app/services/` | 业务校验、模式分发、结果落盘、音色库管理、预置朗读稿（`voice_presets.py`） |
| 核心层 | `app/core/` | 模型生命周期、CosyVoice 封装、异常定义 |
| 工具层 | `app/utils/` | WAV 读写、音频校验（仅依赖标准库 + numpy + soundfile） |

设计要点：

* **模型懒加载 + 单例**：`ModelManager` 保证同一进程只持有一份模型，并用信号量串行化
  推理调用（上游 `model.tts` 非线程安全）。
* **前后端契约单一来源**：`app/services/modes.py` 定义了每种合成模式需要哪些表单字段，
  前端通过 `GET /api/v1/system/modes` 动态渲染表单，避免字段漂移。
* **失败即报错**：模型加载失败时 `ModelManager` 把状态置为 `error` 并保留原始原因，
  HTTP 层返回 503 + 具体原因。代码中**没有任何模拟推理分支**，避免"服务看似正常
  但输出不是人声"。

## 环境变量

见 `.env.example`，所有变量以 `CV_` 为前缀。常用项：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `CV_MODEL_DIR` | `iic/CosyVoice2-0.5B` | 本地目录或 ModelScope repo id |
| `CV_COSYVOICE_REPO` | `../CosyVoice` | 官方仓库路径（含 `third_party/Matcha-TTS`） |
| `CV_PRELOAD_MODEL` | `false` | 启动即加载模型 |
| `CV_FP16` / `CV_LOAD_JIT` / `CV_LOAD_TRT` / `CV_LOAD_VLLM` | `false` | 加速开关 |
| `CV_API_PREFIX` | `/api/v1` | 接口前缀 |
| `CV_CORS_ORIGINS` | `["http://localhost:5173"]` | 允许跨域的前端地址 |
| `CV_DATA_DIR` | `../data` | 数据目录（音色库 / 生成结果 / 临时文件） |

## 与上游对接的三个关键点

这三条都是实际踩过坑后固化下来的，改代码时请勿回退：

### 1. `prompt_wav` 必须传文件路径，不能传 tensor

```python
# ❌ 上游 runtime/python/fastapi/server.py 的旧写法（该文件已过时）
prompt_speech_16k = load_wav(prompt_wav.file, 16000)
cosyvoice.inference_zero_shot(tts_text, prompt_text, prompt_speech_16k)

# ✅ 当前版本
cosyvoice.inference_zero_shot(tts_text, prompt_text, '/abs/path/prompt.wav')
```

`CosyVoiceFrontEnd._extract_speech_feat`(24kHz)、`_extract_speech_token`(16kHz)、
`_extract_spk_embedding`(16kHz) 会各自重新读取文件并按不同采样率重采样，
传 tensor 会抛 `TypeError: Invalid file: tensor(...)`。
实现见 `app/core/cosyvoice_backend.py::_prompt_path`，
回归测试见 `tests/test_backend_contract.py`。

### 2. 没有内置音色的模型必须禁用 `sft` 模式

CosyVoice2 / CosyVoice3 的权重里没有 `spk2info.pt`，`frontend.spk2info` 为空字典，
此时 `frontend_sft()` 会 `KeyError`。因此：

* `ModelManager.modes_payload()` 会在音色列表为空时把 `sft` 标记为不可用；
* `CosyVoiceBackend.supports('sft')` 同样返回 `False`，接口层面直接返回 409 而不是 500。

### 3. 模型加载失败绝不降级

`ModelManager._build_backend()` 不捕获异常：加载失败时 `load()` 会把状态置为 `error`
并把原因放进 `status()["error"]`，`ensure_ready()` 抛出 `ModelNotReadyError`（HTTP 503）。
**不要**再引入任何"加载失败就返回模拟音频"的兜底逻辑 —— 这是本项目修复过的一个真实故障：
用户界面一切正常，拿到的却是蜂鸣音。

回归测试：`tests/test_model_config.py::test_missing_model_dir_never_falls_back_to_fake_audio`
以及 `test_model_manager_exposes_no_mock_switch`（断言配置与状态里不存在任何 mock 开关）。

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

测试通过 `tests/stub_backend.py`（仅存在于 tests/ 的测试替身）注入，
覆盖：音频工具、音色 CRUD、参数校验、一次性合成、流式合成、历史记录与错误码，
无需 GPU 与模型权重。应用运行时不存在该替身，也没有任何模拟推理路径。

## Docker

```bash
# 仅 Web 服务层
docker build -t cosyvoice-web .

# 连推理依赖一起装
docker build --build-arg INSTALL_INFERENCE_DEPS=true -t cosyvoice-web .

# 运行（必须挂载 CosyVoice 仓库与权重，否则会以 state=error 启动并说明原因）
docker run --rm -p 8000:8000 \
  -v /path/to/CosyVoice:/opt/CosyVoice:ro \
  -v /path/to/data:/data \
  cosyvoice-web
```

真实 GPU 推理请把基础镜像换成 CUDA 版本并安装 torch，详见 `Dockerfile` 顶部说明。
