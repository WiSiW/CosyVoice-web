let session = null

function sendMessage(message) {
  return chrome.runtime.sendMessage(message).catch(() => null)
}

async function startSession(message) {
  if (session) throw new Error('已有采集任务正在运行')

  let stream = null
  let audioContext = null
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        mandatory: {
          chromeMediaSource: 'tab',
          chromeMediaSourceId: message.streamId,
        },
      },
      video: false,
    })

    audioContext = new AudioContext()
    const source = audioContext.createMediaStreamSource(stream)
    source.connect(audioContext.destination)
    await audioContext.resume()

    const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find(
      (type) => MediaRecorder.isTypeSupported(type),
    )
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
    const chunks = []
    recorder.addEventListener('dataavailable', (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    })

    session = {
      stream,
      audioContext,
      recorder,
      chunks,
      durationMs: message.durationMs,
      startedAt: performance.now(),
      progressTimer: null,
      stopTimer: null,
      stopping: false,
    }

    recorder.start(250)
    session.progressTimer = window.setInterval(() => {
      if (!session) return
      const elapsedMs = Math.min(session.durationMs, performance.now() - session.startedAt)
      void sendMessage({
        type: 'CAPTURE_OFFSCREEN_PROGRESS',
        elapsedMs,
        durationMs: session.durationMs,
      })
    }, 200)
    session.stopTimer = window.setTimeout(() => {
      void finishSession(false)
    }, session.durationMs)
  } catch (error) {
    session = null
    stream?.getTracks().forEach((track) => track.stop())
    await audioContext?.close().catch(() => undefined)
    throw error
  }
}

async function finishSession(canceled) {
  const active = session
  if (!active || active.stopping) return
  active.stopping = true
  window.clearInterval(active.progressTimer)
  window.clearTimeout(active.stopTimer)

  const blob = await stopRecorder(active)
  await releaseCapture(active)
  session = null

  if (canceled) {
    await sendMessage({ type: 'CAPTURE_OFFSCREEN_CANCELED' })
    return
  }

  try {
    await sendMessage({ type: 'CAPTURE_OFFSCREEN_CONVERTING' })
    const wav = await transcodeToWav(blob)
    const base64 = bytesToBase64(new Uint8Array(await wav.blob.arrayBuffer()))
    await sendMessage({
      type: 'CAPTURE_OFFSCREEN_CAPTURED',
      base64,
      duration: wav.duration,
    })
  } catch (error) {
    await sendMessage({
      type: 'CAPTURE_OFFSCREEN_ERROR',
      message: error instanceof Error ? error.message : String(error),
    })
  }
}

function stopRecorder(active) {
  return new Promise((resolve) => {
    if (active.recorder.state === 'inactive') {
      resolve(new Blob(active.chunks, { type: active.recorder.mimeType || 'audio/webm' }))
      return
    }
    active.recorder.addEventListener(
      'stop',
      () => {
        resolve(new Blob(active.chunks, { type: active.recorder.mimeType || 'audio/webm' }))
      },
      { once: true },
    )
    active.recorder.stop()
  })
}

async function releaseCapture(active) {
  active.stream.getTracks().forEach((track) => track.stop())
  await active.audioContext.close().catch(() => undefined)
}

async function transcodeToWav(blob) {
  if (blob.size === 0) throw new Error('没有采集到页面音频')

  const decodeContext = new AudioContext()
  try {
    const encoded = await blob.arrayBuffer()
    const decoded = await decodeContext.decodeAudioData(encoded)
    const targetSampleRate = 16000
    const frameCount = Math.max(1, Math.round(decoded.duration * targetSampleRate))
    const offline = new OfflineAudioContext(1, frameCount, targetSampleRate)
    const source = offline.createBufferSource()
    source.buffer = decoded
    source.connect(offline.destination)
    source.start()
    const rendered = await offline.startRendering()
    return {
      blob: encodeWav(rendered.getChannelData(0), targetSampleRate),
      duration: rendered.length / targetSampleRate,
    }
  } finally {
    await decodeContext.close().catch(() => undefined)
  }
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  writeAscii(view, 0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  writeAscii(view, 8, 'WAVE')
  writeAscii(view, 12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  writeAscii(view, 36, 'data')
  view.setUint32(40, samples.length * 2, true)

  let offset = 44
  for (const sample of samples) {
    const clamped = Math.max(-1, Math.min(1, sample))
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true)
    offset += 2
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

function writeAscii(view, offset, text) {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index))
  }
}

function bytesToBase64(bytes) {
  let binary = ''
  const chunkSize = 0x8000
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize))
  }
  return btoa(binary)
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.target !== 'offscreen') return false

  if (message.type === 'CAPTURE_OFFSCREEN_START') {
    startSession(message)
      .then(() => sendResponse({ ok: true }))
      .catch((error) => {
        session = null
        sendResponse({
          ok: false,
          message: error instanceof Error ? error.message : String(error),
        })
      })
    return true
  }
  if (message.type === 'CAPTURE_OFFSCREEN_CANCEL') {
    void finishSession(true)
    sendResponse({ ok: true })
    return false
  }
  return false
})
