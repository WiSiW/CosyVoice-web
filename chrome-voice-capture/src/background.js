const OFFSCREEN_PATH = 'offscreen/offscreen.html'
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'

let state = {
  phase: 'idle',
  message: '',
  elapsedMs: 0,
  durationMs: 0,
  captureId: '',
  capturedDuration: 0,
  savedVoice: null,
}
let sampleBase64 = ''

async function publish(patch) {
  state = { ...state, ...patch }
  try {
    await chrome.runtime.sendMessage({ type: 'CAPTURE_STATE', state })
  } catch {
    // The popup can be closed while recording continues.
  }
}

async function ensureOffscreenDocument() {
  const offscreenUrl = chrome.runtime.getURL(OFFSCREEN_PATH)
  const contexts = await chrome.runtime.getContexts({
    contextTypes: ['OFFSCREEN_DOCUMENT'],
    documentUrls: [offscreenUrl],
  })
  if (contexts.length > 0) return

  await chrome.offscreen.createDocument({
    url: OFFSCREEN_PATH,
    reasons: ['USER_MEDIA', 'AUDIO_PLAYBACK'],
    justification: '采集并试听当前标签页音频，用于保存音色样本',
  })
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) throw new Error('没有找到当前标签页')
  if (tab.url?.startsWith('chrome://') || tab.url?.startsWith('edge://')) {
    throw new Error('Chrome 内部页面不支持音频采集')
  }
  return tab
}

async function startCapture({ durationSeconds = 10 } = {}) {
  if (state.phase === 'capturing' || state.phase === 'converting') {
    return { ok: false, message: '已有采集任务正在进行' }
  }

  const durationMs = Math.max(3, Math.min(30, Number(durationSeconds) || 10)) * 1000
  sampleBase64 = ''
  try {
    await publish({
      phase: 'capturing',
      message: '正在连接当前标签页音频',
      elapsedMs: 0,
      durationMs,
      captureId: '',
      capturedDuration: 0,
      savedVoice: null,
    })

    const tab = await getActiveTab()
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id })
    await ensureOffscreenDocument()
    const response = await chrome.runtime.sendMessage({
      target: 'offscreen',
      type: 'CAPTURE_OFFSCREEN_START',
      streamId,
      durationMs,
      tabTitle: tab.title || '',
    })
    if (!response?.ok) throw new Error(response?.message || '无法启动音频采集')
    return { ok: true }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await publish({ phase: 'error', message })
    return { ok: false, message }
  }
}

async function cancelCapture() {
  if (state.phase !== 'capturing') return { ok: true }
  try {
    await chrome.runtime.sendMessage({
      target: 'offscreen',
      type: 'CAPTURE_OFFSCREEN_CANCEL',
    })
  } catch {
    // The capture may already have completed.
  }
  sampleBase64 = ''
  await publish({ phase: 'idle', message: '已取消', elapsedMs: 0 })
  return { ok: true }
}

function base64ToBytes(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes
}

async function saveVoice(options) {
  if (!sampleBase64) throw new Error('没有可保存的音频，请先完成采集')

  const name = String(options?.name || '').trim()
  if (!name) throw new Error('请填写音色名称')
  const promptText = String(options?.promptText || '').trim()
  const autoRegister = Boolean(options?.autoRegister)
  if (autoRegister && !promptText) {
    throw new Error('自动注册需要参考文本；取消勾选后仍可只保存音色样本')
  }

  const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE_URL,
  })
  const baseUrl = String(apiBaseUrl).replace(/\/+$/, '')
  const bytes = base64ToBytes(sampleBase64)
  const form = new FormData()
  form.append('name', name)
  form.append('audio', new Blob([bytes], { type: 'audio/wav' }), 'page-capture.wav')
  form.append('prompt_text', promptText)
  form.append('description', '由页面音色采集器从当前标签页采集')
  form.append('language', String(options?.language || '中文'))
  form.append('source', 'record')
  form.append('auto_register', String(autoRegister))

  await publish({ phase: 'saving', message: '正在保存到音色库' })
  let response
  try {
    response = await fetch(`${baseUrl}/voices`, { method: 'POST', body: form })
  } catch {
    await publish({ phase: 'captured', message: '后端未连接，音频仍可下载' })
    throw new Error(`无法连接后端 ${baseUrl}`)
  }
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    await publish({ phase: 'captured', message: '保存失败，音频仍可下载' })
    throw new Error(payload?.error?.message || `后端返回 ${response.status}`)
  }

  await publish({
    phase: 'captured',
    message: `音色「${payload.name}」已保存`,
    savedVoice: payload,
  })
  return payload
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.target && message.target !== 'background') return false

  if (message?.type === 'CAPTURE_START') {
    startCapture(message).then(sendResponse)
    return true
  }
  if (message?.type === 'CAPTURE_CANCEL') {
    cancelCapture().then(sendResponse)
    return true
  }
  if (message?.type === 'CAPTURE_GET_STATE') {
    sendResponse({ ok: true, state })
    return false
  }
  if (message?.type === 'CAPTURE_GET_SAMPLE') {
    sendResponse({
      ok: Boolean(sampleBase64),
      base64: sampleBase64,
      duration: state.capturedDuration,
    })
    return false
  }
  if (message?.type === 'CAPTURE_SAVE_VOICE') {
    saveVoice(message.options)
      .then((voice) => sendResponse({ ok: true, voice }))
      .catch((error) =>
        sendResponse({
          ok: false,
          message: error instanceof Error ? error.message : String(error),
        }),
      )
    return true
  }
  if (message?.type === 'CAPTURE_OFFSCREEN_PROGRESS') {
    void publish({
      phase: 'capturing',
      message: '正在采集页面音频',
      elapsedMs: message.elapsedMs,
      durationMs: message.durationMs,
    })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'CAPTURE_OFFSCREEN_CONVERTING') {
    void publish({ phase: 'converting', message: '正在转换为 WAV' })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'CAPTURE_OFFSCREEN_CAPTURED') {
    sampleBase64 = message.base64 || ''
    void publish({
      phase: sampleBase64 ? 'captured' : 'error',
      message: sampleBase64 ? '采集完成' : '没有采集到音频',
      captureId: `${Date.now()}`,
      capturedDuration: Number(message.duration || 0),
      durationMs: Number(message.duration || 0) * 1000,
      savedVoice: null,
    })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'CAPTURE_OFFSCREEN_ERROR') {
    void publish({ phase: 'error', message: message.message || '采集失败' })
    sendResponse({ ok: true })
    return false
  }
  return false
})
