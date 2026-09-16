import { onBeforeUnmount, ref } from 'vue'

const PREFERRED_MIME_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/ogg;codecs=opus',
  'audio/mp4',
]

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined
  return PREFERRED_MIME_TYPES.find((type) => MediaRecorder.isTypeSupported?.(type))
}

/** 麦克风录音，输出原始 Blob（调用方再用 prepareAudio 转成 WAV）。 */
export function useAudioRecorder(maxSeconds = 30) {
  const recording = ref(false)
  const seconds = ref(0)
  const error = ref('')
  let recorder: MediaRecorder | null = null
  let stream: MediaStream | null = null
  let chunks: BlobPart[] = []
  let timer: number | null = null

  function cleanup(): void {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
    recorder = null
    recording.value = false
  }

  async function start(): Promise<void> {
    error.value = ''
    if (recording.value) return
    if (!navigator.mediaDevices?.getUserMedia) {
      error.value = '当前浏览器不支持录音，请改用上传音频文件'
      throw new Error(error.value)
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      })
    } catch {
      error.value = '无法访问麦克风，请检查浏览器权限设置'
      throw new Error(error.value)
    }

    chunks = []
    const mimeType = pickMimeType()
    recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    recorder.start(200)
    recording.value = true
    seconds.value = 0

    timer = window.setInterval(() => {
      seconds.value += 0.2
      if (seconds.value >= maxSeconds) void stop()
    }, 200)
  }

  function stop(): Promise<Blob | null> {
    return new Promise((resolve) => {
      const active = recorder
      if (!active || active.state === 'inactive') {
        cleanup()
        resolve(null)
        return
      }
      active.onstop = () => {
        const blob = new Blob(chunks, { type: active.mimeType || 'audio/webm' })
        cleanup()
        resolve(blob.size > 0 ? blob : null)
      }
      active.stop()
    })
  }

  onBeforeUnmount(() => {
    void stop()
  })

  return { recording, seconds, error, start, stop }
}
