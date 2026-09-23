# CosyVoice Web Frontend

Vue 3 + Vite + TypeScript + Pinia 实现的语音合成控制台。

完整项目说明见仓库根目录 `README.md`。

## 启动

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 类型检查 + 生产构建到 dist/
npm run preview    # 预览构建产物
npm run typecheck  # 仅类型检查
```

开发服务器已配置 `/api` → `http://127.0.0.1:8000` 代理，默认无需处理 CORS。
若后端部署在其他地址，可在界面「设置」页修改 API 地址（持久化到 localStorage），
或通过 `frontend/.env` 的 `VITE_API_BASE_URL` 指定。

## 目录说明

```
src/
├── api/            # axios 实例 + 各领域接口封装 + 流式 fetch
│   ├── client.ts      请求封装与统一错误对象 RequestError
│   ├── runtime.ts     API 地址运行时配置（支持界面内热切换）
│   ├── system.ts      健康检查 / 系统信息 / 模式 / 模型加载
│   ├── voices.ts      音色库 CRUD
│   └── tts.ts         合成（一次性 / 流式）与历史记录
├── components/     # 通用组件
│   ├── AudioInput.vue     上传 / 录音二合一，自动转码为 16k WAV
│   ├── AudioPlayer.vue    自绘进度条的播放器
│   ├── ModeTabs.vue       合成模式切换
│   ├── VoicePicker.vue    预训练音色 + 自定义音色统一选择
│   └── ResultCard.vue     生成结果卡片
├── composables/    # 组合式函数
│   ├── usePcmStreamPlayer.ts  流式 PCM 边收边播 + 合并导出 WAV
│   ├── useAudioRecorder.ts    MediaRecorder 录音封装
│   └── useToast.ts            轻量全局提示
├── stores/         # Pinia
│   ├── settings.ts    主题 / 默认模式 / 流式开关（localStorage 持久化）
│   ├── system.ts      模型与系统状态
│   ├── voices.ts      音色库
│   └── history.ts     生成记录（本地 + 服务端同步）
├── utils/
│   ├── audio.ts       WAV 编解码、重采样、PCM 转换
│   └── format.ts      时间 / 体积 / 文本格式化
└── views/          # 页面：合成 / 音色库 / 记录 / 设置
```

## 关键技术点

### 参考音频统一转码

浏览器录音（`MediaRecorder`）与用户上传的 mp3 / m4a 等格式 TorchAudio 往往无法直接读取，
因此 `utils/audio.ts#prepareAudio` 会：

1. 用 `AudioContext.decodeAudioData` 解码；
2. 用 `OfflineAudioContext(1, frames, 16000)` 重采样为 **16kHz 单声道**；
3. 编码为标准 16bit PCM WAV 后再上传。

### 流式播放

`usePcmStreamPlayer` 读取 `fetch` 的 `ReadableStream`：

* 处理跨分片的奇数字节，保证 int16 对齐；
* 逐块 `createBuffer` → `AudioBufferSourceNode`，按 `nextStartTime` 顺序排队播放；
* 同时缓存全部采样，结束后可合并为 WAV 下载，并记录 RTF 供参考。

### 生成记录的"清空"语义

«清空记录» 会先调用 `DELETE /api/v1/tts/history` 删除**服务端**音频文件，再清空本地
localStorage 列表。不能只清本地 —— 列表是服务端记录的视图，下次 `syncRemote()`
会把它们重新补回来，那样"清空"看起来就是无效的（这是修复过的一个真实问题）。

### 主题

`styles/main.css` 中通过 CSS 变量定义深浅色主题，`useSettingsStore.state.theme`
写入 `document.documentElement.dataset.theme` 即时切换。
