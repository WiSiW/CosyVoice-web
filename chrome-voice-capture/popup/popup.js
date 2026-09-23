const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'

const elements = {
  backendStatus: document.querySelector('#backend-status'),
  settingsButton: document.querySelector('#settings-button'),
  durationControl: document.querySelector('#duration-control'),
  progressPanel: document.querySelector('#progress-panel'),
  progressTitle: document.querySelector('#progress-title'),
  progressTime: document.querySelector('#progress-time'),
  progressBar: document.querySelector('#progress-bar'),
  errorPanel: document.querySelector('#error-panel'),
  errorTitle: document.querySelector('#error-title'),
  errorMessage: document.querySelector('#error-message'),
  samplePanel: document.querySelector('#sample-panel'),
  sampleDuration: document.querySelector('#sample-duration'),
  audioPreview: document.querySelector('#audio-preview'),
  sampleMessage: document.querySelector('#sample-message'),
  downloadButton: document.querySelector('#download-button'),
  voiceName: document.querySelector('#voice-name'),
  voiceLanguage: document.querySelector('#voice-language'),
  promptText: document.querySelector('#prompt-text'),
  autoRegister: document.querySelector('#auto-register'),
  saveButton: document.querySelector('#save-button'),
  startButton: document.querySelector('#start-button'),
  cancelButton: document.querySelector('#cancel-button'),
}

let selectedDuration = 10
let currentState = { phase: 'idle' }
let previewCaptureId = ''
let previewObjectUrl = ''

function sendMessage(message) {
  return chrome.runtime.sendMessage(message)
}

function setActiveDuration(seconds) {
  selectedDuration = seconds
  elements.durationControl.querySelectorAll('button').forEach((button) => {
    button.classList.toggle('active', Number(button.dataset.duration) === seconds)
  })
}

function render(state) {
  currentState = state || { phase: 'idle' }
  const phase = currentState.phase || 'idle'
  const busy = phase === 'capturing' || phase === 'converting' || phase === 'saving'
  const hasSample = Boolean(currentState.captureId)

  elements.startButton.disabled = busy
  elements.startButton.textContent =
    phase === 'converting' ? '转换中' : phase === 'saving' ? '保存中' : '开始采集'
  elements.cancelButton.hidden = phase !== 'capturing'
  elements.progressPanel.hidden = !busy
  elements.errorPanel.hidden = phase !== 'error'
  elements.samplePanel.hidden = !hasSample || phase === 'capturing' || phase === 'converting'

  if (busy) {
    const elapsed = Math.max(0, currentState.elapsedMs || 0)
    const duration = Math.max(1, currentState.durationMs || selectedDuration * 1000)
    const ratio = phase === 'capturing' ? Math.min(1, elapsed / duration) : 1
    elements.progressTitle.textContent = currentState.message || '正在处理'
    elements.progressTime.textContent =
      phase === 'capturing'
        ? `${(elapsed / 1000).toFixed(1)} / ${(duration / 1000).toFixed(1)} 秒`
        : '处理中'
    elements.progressBar.style.width = `${Math.round(ratio * 100)}%`
  }

  if (phase === 'error') {
    elements.errorTitle.textContent = hasSample ? '保存失败' : '采集失败'
    elements.errorMessage.textContent = currentState.message || '请稍后重试'
  }
  if (['captured', 'saving'].includes(phase)) {
    elements.sampleDuration.textContent = `${Number(currentState.capturedDuration || 0).toFixed(1)} 秒`
    void loadPreview()
  }
  if (hasSample) {
    elements.sampleMessage.textContent = currentState.message || ''
  }
}

async function loadPreview() {
  const captureId = currentState.captureId
  if (!captureId || captureId === previewCaptureId) return

  const response = await sendMessage({ type: 'CAPTURE_GET_SAMPLE' })
  if (!response?.ok) return
  const blob = base64ToBlob(response.base64)
  if (previewObjectUrl) URL.revokeObjectURL(previewObjectUrl)
  previewObjectUrl = URL.createObjectURL(blob)
  previewCaptureId = captureId
  elements.audioPreview.src = previewObjectUrl
}

function base64ToBlob(base64) {
  const binary = atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new Blob([bytes], { type: 'audio/wav' })
}

async function loadBackendStatus() {
  const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE_URL,
  })
  const baseUrl = String(apiBaseUrl).replace(/\/+$/, '')
  try {
    const response = await fetch(`${baseUrl}/timbre/status`)
    const payload = await response.json()
    if (!response.ok) throw new Error()
    const state = payload.ready ? '模型已就绪' : `模型${payload.model_state}`
    elements.backendStatus.textContent = `${state} · 音色库 ${payload.voice_count} 个`
  } catch {
    elements.backendStatus.textContent = '后端未连接，仍可采集和下载 WAV'
  }
}

async function loadLanguages() {
  const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE_URL,
  })
  const baseUrl = String(apiBaseUrl).replace(/\/+$/, '')
  let languages = ['中文', '英语', '日语', '韩语', '粤语', '其他']
  try {
    const response = await fetch(`${baseUrl}/voices/languages`)
    if (response.ok) languages = await response.json()
  } catch {
    // Offline capture still works with the built-in language choices.
  }
  elements.voiceLanguage.replaceChildren(
    ...languages.map((language) => {
      const option = document.createElement('option')
      option.value = language
      option.textContent = language
      return option
    }),
  )
}

function syncAutoRegisterState() {
  const hasPromptText = Boolean(elements.promptText.value.trim())
  if (!hasPromptText) elements.autoRegister.checked = false
  elements.autoRegister.disabled = !hasPromptText
}

elements.durationControl.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-duration]')
  if (!button || ['capturing', 'converting', 'saving'].includes(currentState.phase)) return
  setActiveDuration(Number(button.dataset.duration))
})

elements.startButton.addEventListener('click', async () => {
  const response = await sendMessage({
    type: 'CAPTURE_START',
    durationSeconds: selectedDuration,
  })
  if (!response?.ok) render({ phase: 'error', message: response?.message || '无法开始采集' })
})

elements.cancelButton.addEventListener('click', async () => {
  await sendMessage({ type: 'CAPTURE_CANCEL' })
  render({ phase: 'idle' })
})

elements.settingsButton.addEventListener('click', () => chrome.runtime.openOptionsPage())

elements.downloadButton.addEventListener('click', async () => {
  const response = await sendMessage({ type: 'CAPTURE_GET_SAMPLE' })
  if (!response?.ok) return
  const url = URL.createObjectURL(base64ToBlob(response.base64))
  const link = document.createElement('a')
  link.href = url
  link.download = `page-timbre-${new Date().toISOString().replace(/[:.]/g, '-')}.wav`
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
})

elements.saveButton.addEventListener('click', async () => {
  const promptText = elements.promptText.value.trim()
  const response = await sendMessage({
    type: 'CAPTURE_SAVE_VOICE',
    options: {
      name: elements.voiceName.value,
      language: elements.voiceLanguage.value,
      promptText,
      autoRegister: Boolean(promptText) && elements.autoRegister.checked,
    },
  })
  if (!response?.ok) {
    render({ ...currentState, phase: 'error', message: response?.message || '保存失败' })
  }
})

elements.promptText.addEventListener('input', syncAutoRegisterState)

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === 'CAPTURE_STATE') render(message.state)
})

async function initialize() {
  const response = await sendMessage({ type: 'CAPTURE_GET_STATE' })
  render(response?.state)
  elements.voiceName.value = `页面采集 ${new Date()
    .toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
    .replace(/[/:]/g, '')}`
  syncAutoRegisterState()
  void loadBackendStatus()
  void loadLanguages()
}

void initialize()
