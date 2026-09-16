import { onBeforeUnmount, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { synthesizeStream, type SynthesisPayload } from '@/api/tts'
import { int16ToFloat32, pcmBytesToInt16, pcmChunksToWavBlob } from '@/utils/audio'

/**
 * 边收边播的 PCM 播放器。
 *
 * 后端以 int16 PCM 分片流式返回，这里把每个分片解码成 Float32 后
 * 依次排进 Web Audio 的时间轴，实现「首包即出声」的体验；
 * 同时缓存全部分片，结束后可导出完整 WAV。
 */
export function usePcmStreamPlayer() {
  const streaming = ref(false)
  const playing = ref(false)
  const receivedDuration = ref(0)
  const error = ref('')

  let context: AudioContext | null = null
  let gainNode: GainNode | null = null
  let sources: AudioBufferSourceNode[] = []
  let nextStartTime = 0
  let chunks: Float32Array[] = []
  let pendingByte: Uint8Array | null = null
  let sampleRate = 22050
  let controller: AbortController | null = null
  let audioId = ''

  function ensureContext(): AudioContext {
    if (!context || context.state === 'closed') {
      const Ctor =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
      if (!Ctor) throw new Error('当前浏览器不支持 Web Audio API')
      context = new Ctor()
      gainNode = context.createGain()
      gainNode.connect(context.destination)
      nextStartTime = 0
    }
    if (context.state === 'suspended') void context.resume()
    return context
  }

  function schedule(bytes: Uint8Array, rate: number): void {
    // stop() 之后仍可能有在途分片，直接丢弃避免"停了又响"
    if (!controller) return
    sampleRate = rate
    let data = bytes
    if (pendingByte && pendingByte.length) {
      const merged = new Uint8Array(pendingByte.length + data.length)
      merged.set(pendingByte, 0)
      merged.set(data, pendingByte.length)
      data = merged
    }
    pendingByte = null
    if (data.length % 2 !== 0) {
      pendingByte = data.slice(data.length - 1)
      data = data.slice(0, data.length - 1)
    }
    if (!data.length) return

    const samples = int16ToFloat32(pcmBytesToInt16(data))
    chunks.push(samples)
    receivedDuration.value += samples.length / sampleRate

    const ctx = ensureContext()
    const buffer = ctx.createBuffer(1, samples.length, sampleRate)
    buffer.copyToChannel(samples, 0)

    const source = ctx.createBufferSource()
    source.buffer = buffer
    source.connect(gainNode ?? ctx.destination)

    const startAt = Math.max(ctx.currentTime + 0.03, nextStartTime)
    source.start(startAt)
    nextStartTime = startAt + buffer.duration

    sources.push(source)
    playing.value = true
    source.onended = () => {
      sources = sources.filter((item) => item !== source)
      if (sources.length === 0 && !streaming.value) playing.value = false
    }
  }

  async function start(payload: SynthesisPayload): Promise<{ audioId: string }> {
    stop()
    streaming.value = true
    playing.value = false
    receivedDuration.value = 0
    error.value = ''
    chunks = []
    pendingByte = null
    audioId = ''
    controller = new AbortController()

    try {
      const result = await synthesizeStream(payload, schedule, controller.signal)
      sampleRate = result.sampleRate
      audioId = result.audioId
      return { audioId }
    } catch (err) {
      if ((err as Error)?.name === 'AbortError') return { audioId: '' }
      error.value = errorMessage(err)
      throw err
    } finally {
      streaming.value = false
      if (sources.length === 0) playing.value = false
    }
  }

  function stop(): void {
    controller?.abort()
    controller = null
    sources.forEach((source) => {
      try {
        source.stop()
      } catch {
        /* 已结束的节点忽略 */
      }
    })
    sources = []
    playing.value = false
    streaming.value = false
    if (context && context.state !== 'closed') {
      void context.close()
    }
    context = null
    gainNode = null
    nextStartTime = 0
  }

  function toWavBlob(): Blob | null {
    if (!chunks.length) return null
    return pcmChunksToWavBlob(chunks, sampleRate)
  }

  function reset(): void {
    stop()
    chunks = []
    receivedDuration.value = 0
    error.value = ''
  }

  onBeforeUnmount(() => stop())

  return { streaming, playing, receivedDuration, error, start, stop, reset, toWavBlob, audioId: () => audioId }
}
