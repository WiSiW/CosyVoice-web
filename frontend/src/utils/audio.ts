/** 浏览器端音频处理：统一转码为 16kHz 单声道 WAV，保证后端可解析。 */

import type { PreparedAudio } from '@/types'

export const TARGET_SAMPLE_RATE = 16000

/** float32 [-1,1] -> int16 */
export function float32ToInt16(input: Float32Array): Int16Array {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]))
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  return output
}

/** int16 -> float32 [-1,1] */
export function int16ToFloat32(input: Int16Array): Float32Array {
  const output = new Float32Array(input.length)
  for (let i = 0; i < input.length; i += 1) {
    output[i] = input[i] / 0x8000
  }
  return output
}

/** 把 Uint8Array 按小端序解析为 Int16Array（自动丢弃最后一个不完整字节） */
export function pcmBytesToInt16(bytes: Uint8Array): Int16Array {
  const usable = bytes.byteLength - (bytes.byteLength % 2)
  if (usable <= 0) return new Int16Array(0)
  const view = new DataView(bytes.buffer, bytes.byteOffset, usable)
  const output = new Int16Array(usable / 2)
  for (let i = 0; i < output.length; i += 1) {
    output[i] = view.getInt16(i * 2, true)
  }
  return output
}

export function concatFloat32(chunks: Float32Array[], totalLength?: number): Float32Array {
  const total = totalLength ?? chunks.reduce((sum, chunk) => sum + chunk.length, 0)
  const merged = new Float32Array(total)
  let offset = 0
  for (const chunk of chunks) {
    merged.set(chunk, offset)
    offset += chunk.length
  }
  return merged
}

/** 将多声道浮点采样编码为 16bit PCM WAV */
export function encodeWav(channels: Float32Array[], sampleRate: number): Blob {
  const channelCount = channels.length
  const frameCount = channels[0]?.length ?? 0
  const bytesPerSample = 2
  const blockAlign = channelCount * bytesPerSample
  const dataSize = frameCount * blockAlign
  const buffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buffer)

  const writeString = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i += 1) view.setUint8(offset + i, text.charCodeAt(i))
  }

  writeString(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  writeString(8, 'WAVE')
  writeString(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, channelCount, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * blockAlign, true)
  view.setUint16(32, blockAlign, true)
  view.setUint16(34, 16, true)
  writeString(36, 'data')
  view.setUint32(40, dataSize, true)

  let offset = 44
  for (let frame = 0; frame < frameCount; frame += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      const sample = Math.max(-1, Math.min(1, channels[channel][frame] ?? 0))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += bytesPerSample
    }
  }

  return new Blob([buffer], { type: 'audio/wav' })
}

let sharedContext: AudioContext | null = null

function getAudioContext(): AudioContext {
  if (!sharedContext || sharedContext.state === 'closed') {
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
    if (!Ctor) throw new Error('当前浏览器不支持 Web Audio API')
    sharedContext = new Ctor()
  }
  return sharedContext
}

/**
 * 把任意浏览器可解码的音频（mp3 / m4a / webm 录音等）
 * 转成 16kHz 单声道 WAV，并返回可直接提交给后端的 File。
 */
export async function prepareAudio(blob: Blob, filename = 'prompt.wav'): Promise<PreparedAudio> {
  const arrayBuffer = await blob.arrayBuffer()
  const context = getAudioContext()

  let decoded: AudioBuffer
  try {
    decoded = await context.decodeAudioData(arrayBuffer.slice(0))
  } catch {
    throw new Error('无法解码该音频文件，请换用 WAV / MP3 / M4A 等常见格式')
  }

  const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_SAMPLE_RATE))
  const offline = new OfflineAudioContext(1, frames, TARGET_SAMPLE_RATE)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start(0)

  const rendered = await offline.startRendering()
  const wavBlob = encodeWav([rendered.getChannelData(0)], TARGET_SAMPLE_RATE)

  return {
    file: new File([wavBlob], filename.replace(/\.[^.]+$/, '') + '.wav', { type: 'audio/wav' }),
    url: URL.createObjectURL(wavBlob),
    duration: rendered.duration,
    sampleRate: TARGET_SAMPLE_RATE,
    source: 'upload',
  }
}

/** 把 PCM 分片合并成可下载的 WAV */
export function pcmChunksToWavBlob(chunks: Float32Array[], sampleRate: number): Blob {
  return encodeWav([concatFloat32(chunks)], sampleRate)
}
