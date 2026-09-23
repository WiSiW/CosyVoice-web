import type { AudioItem, ModeId } from '@/types'

import { RequestError, del, get } from './client'
import { apiUrl } from './runtime'

export interface SynthesisPayload {
  mode: ModeId
  ttsText?: string
  spkId?: string
  voiceId?: string
  /** 同时把本次上传的参考音频保存进音色库（仅 3s 极速复刻模式有效） */
  saveVoice?: boolean
  voiceName?: string
  promptText?: string
  instructText?: string
  speed?: number
  seed?: number | null
  textFrontend?: boolean
  promptAudio?: Blob | null
  promptFilename?: string
  sourceAudio?: Blob | null
  sourceFilename?: string
}

export interface SynthesisResult {
  blob: Blob
  audioId: string
  sampleRate: number
  duration: number
  remoteUrl: string
  /** 若请求里带了 saveVoice，这里返回新建的音色 id */
  voiceId: string
}

export function toFormData(payload: SynthesisPayload): FormData {
  const form = new FormData()
  form.append('mode', payload.mode)
  form.append('tts_text', payload.ttsText ?? '')
  form.append('spk_id', payload.spkId ?? '')
  form.append('prompt_text', payload.promptText ?? '')
  form.append('instruct_text', payload.instructText ?? '')
  form.append('voice_id', payload.voiceId ?? '')
  form.append('save_voice', String(payload.saveVoice ?? false))
  form.append('voice_name', payload.voiceName ?? '')
  form.append('speed', String(payload.speed ?? 1))
  form.append('text_frontend', String(payload.textFrontend ?? true))
  if (payload.seed !== null && payload.seed !== undefined) {
    form.append('seed', String(payload.seed))
  }
  if (payload.promptAudio) {
    form.append('prompt_wav', payload.promptAudio, payload.promptFilename || 'prompt.wav')
  }
  if (payload.sourceAudio) {
    form.append('source_wav', payload.sourceAudio, payload.sourceFilename || 'source.wav')
  }
  return form
}

/** 一次性合成，返回完整 WAV 文件 */
export async function synthesize(payload: SynthesisPayload): Promise<SynthesisResult> {
  const response = await fetch(apiUrl('/tts/synthesize'), {
    method: 'POST',
    body: toFormData(payload),
  })

  if (!response.ok) {
    throw await toRequestError(response)
  }

  const blob = await response.blob()
  return {
    blob,
    audioId: response.headers.get('X-Audio-Id') ?? '',
    sampleRate: Number(response.headers.get('X-Sample-Rate') ?? 22050),
    duration: Number(response.headers.get('X-Duration') ?? 0),
    remoteUrl: response.headers.get('X-Audio-Url') ?? '',
    voiceId: response.headers.get('X-Voice-Id') ?? '',
  }
}

/** 流式合成：每收到一个 PCM 分片就回调一次 */
export async function synthesizeStream(
  payload: SynthesisPayload,
  onChunk: (chunk: Uint8Array, sampleRate: number) => void,
  signal?: AbortSignal,
): Promise<{ sampleRate: number; audioId: string; voiceId: string }> {
  const response = await fetch(apiUrl('/tts/stream'), {
    method: 'POST',
    body: toFormData(payload),
    signal,
    headers: { Accept: 'application/octet-stream' },
  })

  if (!response.ok || !response.body) {
    throw await toRequestError(response)
  }

  const sampleRate = Number(response.headers.get('X-Sample-Rate') ?? 22050)
  const audioId = response.headers.get('X-Audio-Id') ?? ''
  const voiceId = response.headers.get('X-Voice-Id') ?? ''
  const reader = response.body.getReader()

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      if (value && value.length) onChunk(value, sampleRate)
    }
  } finally {
    reader.releaseLock()
  }

  return { sampleRate, audioId, voiceId }
}

export function fetchHistory(limit = 50): Promise<AudioItem[]> {
  return get('/tts/history', { params: { limit } })
}

export function deleteAudio(audioId: string): Promise<void> {
  return del(`/tts/audio/${audioId}`)
}

/** 清空服务端全部生成记录（同时删除音频文件） */
export function clearHistory(): Promise<{ deleted: number }> {
  return del<{ deleted: number }>('/tts/history')
}

async function toRequestError(response: Response): Promise<RequestError> {
  let message = `请求失败 (${response.status})`
  let code = 'http_error'
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string } }
    if (body?.error?.message) {
      message = body.error.message
      code = body.error.code ?? code
    }
  } catch {
    /* 响应不是 JSON，保留默认提示 */
  }
  return new RequestError(message, code, response.status)
}
