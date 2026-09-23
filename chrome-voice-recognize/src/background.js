const OFFSCREEN_PATH = 'offscreen/offscreen.html'
const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'

let state = {
  phase: 'idle',
  message: '',
  elapsedMs: 0,
  durationMs: 0,
  result: null,
}

async function publish(patch) {
  state = { ...state, ...patch }
  try {
    await chrome.runtime.sendMessage({ type: 'TIMBRE_STATE', state })
  } catch {
    // Popup may be closed; the next popup open reads the current state.
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
    justification: '采集并试听当前标签页音频，用于本地音色识别',
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

async function startCapture({ durationSeconds = 8 } = {}) {
  if (state.phase === 'capturing' || state.phase === 'analyzing') {
    return { ok: false, message: '已有识别任务正在进行' }
  }

  const durationMs = Math.max(3, Math.min(20, Number(durationSeconds) || 8)) * 1000
  try {
    await publish({
      phase: 'capturing',
      message: '正在连接当前标签页音频',
      elapsedMs: 0,
      durationMs,
      result: null,
    })

    const tab = await getActiveTab()
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id })
    await ensureOffscreenDocument()
    const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
      apiBaseUrl: DEFAULT_API_BASE_URL,
    })

    const response = await chrome.runtime.sendMessage({
      target: 'offscreen',
      type: 'TIMBRE_OFFSCREEN_START',
      streamId,
      durationMs,
      tabTitle: tab.title || '',
      apiBaseUrl,
    })
    if (!response?.ok) throw new Error(response?.message || '无法启动音频采集')
    return { ok: true }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    await publish({ phase: 'error', message, result: null })
    return { ok: false, message }
  }
}

async function cancelCapture() {
  if (state.phase !== 'capturing') return { ok: true }
  try {
    await chrome.runtime.sendMessage({
      target: 'offscreen',
      type: 'TIMBRE_OFFSCREEN_CANCEL',
    })
  } catch {
    // The offscreen document may already have finished.
  }
  await publish({ phase: 'idle', message: '已取消', elapsedMs: 0, result: null })
  return { ok: true }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.target && message.target !== 'background') return false

  if (message?.type === 'TIMBRE_START') {
    startCapture(message).then(sendResponse)
    return true
  }
  if (message?.type === 'TIMBRE_CANCEL') {
    cancelCapture().then(sendResponse)
    return true
  }
  if (message?.type === 'TIMBRE_GET_STATE') {
    sendResponse({ ok: true, state })
    return false
  }
  if (message?.type === 'TIMBRE_OFFSCREEN_PROGRESS') {
    void publish({
      phase: 'capturing',
      message: '正在采集页面音频',
      elapsedMs: message.elapsedMs,
      durationMs: message.durationMs,
    })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'TIMBRE_OFFSCREEN_ANALYZING') {
    void publish({ phase: 'analyzing', message: message.message || '正在识别音色' })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'TIMBRE_OFFSCREEN_RESULT') {
    void publish({ phase: 'result', message: '', result: message.result })
    sendResponse({ ok: true })
    return false
  }
  if (message?.type === 'TIMBRE_OFFSCREEN_ERROR') {
    void publish({ phase: 'error', message: message.message || '识别失败', result: null })
    sendResponse({ ok: true })
    return false
  }
  return false
})
