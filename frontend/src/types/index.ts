/** 与后端 /api/v1 接口一一对应的类型定义。 */

export type ModelState = 'unloaded' | 'loading' | 'ready' | 'error'

export type ModeId = 'sft' | 'zero_shot' | 'cross_lingual' | 'instruct2' | 'instruct' | 'vc'

/** 后端返回的模式描述，前端据此动态渲染表单 */
export interface ModeSpec {
  id: ModeId
  label: string
  description: string
  fields: ModeField[]
  field_labels: Record<string, string>
  supports_stream: boolean
  supports_speed: boolean
  required_family: string | null
  note: string
  available: boolean
}

export type ModeField =
  | 'text'
  | 'speaker'
  | 'prompt_text'
  | 'prompt_audio'
  | 'source_audio'
  | 'instruct_text'

export interface ModelStatus {
  state: ModelState
  kind: string | null
  device: 'cpu' | 'cuda' | string
  family: string | null
  sample_rate: number | null
  note: string | null
  model_dir: string
  model_source: string
  error: string | null
  loaded_at: string | null
  load_seconds: number | null
  inference_queue: number
}

export interface SystemInfo {
  app: string
  version: string
  api_prefix: string
  model: ModelStatus
  speakers: string[]
  voices: number
  limits: {
    max_upload_mb: number
    max_prompt_seconds: number
    min_prompt_seconds: number
    max_text_length: number
    speed: { min: number; max: number }
  }
  languages: string[]
}

export interface VoiceAudio {
  filename: string
  original_filename?: string | null
  duration: number
  sample_rate: number
  channels: number
  format: string
  size: number
}

export interface Voice {
  id: string
  name: string
  description: string
  prompt_text: string
  language: string
  source: string
  created_at: string
  updated_at: string
  audio: VoiceAudio
  registered: boolean
  builtin: boolean
  runtime_spk_id: string | null
}

/** 各语种的预置朗读稿（参考文本必须与参考音频逐字一致，故做成朗读稿） */
export interface VoicePreset {
  language: string
  text: string
  target_seconds: number
  note: string
}

export interface VoicePresetsResponse {
  presets: VoicePreset[]
  fallback_note: string
}

export interface VoiceUpdatePayload {
  name?: string
  description?: string
  prompt_text?: string
  language?: string
}

export interface AudioItem {
  audio_id: string
  url: string
  created_at: string
  size: number
  filename: string
}

/** 前端已经解码 / 转码为 16k 单声道 WAV 的参考音频 */
export interface PreparedAudio {
  file: File
  url: string
  duration: number
  sampleRate: number
  source: 'upload' | 'record'
}

/** 一次合成请求的表单状态 */
export interface SynthesisForm {
  mode: ModeId
  ttsText: string
  spkId: string
  voiceId: string
  promptText: string
  instructText: string
  speed: number
  seed: number | null
  textFrontend: boolean
}

/** 生成记录（服务端历史 + 本次会话结果） */
export interface GenerationItem {
  id: string
  mode: ModeId | string
  modeLabel: string
  text: string
  voiceLabel: string
  duration: number
  createdAt: string
  /** 服务端可访问的地址 */
  remoteUrl?: string
  /** 本地 blob 地址，便于立即播放 */
  localUrl?: string
  sampleRate?: number
  rtf?: number
}

export interface ApiError {
  code: string
  message: string
  detail?: unknown
}
