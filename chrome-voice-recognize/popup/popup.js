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
  errorMessage: document.querySelector('#error-message'),
  resultPanel: document.querySelector('#result-panel'),
  resultBadge: document.querySelector('#result-badge'),
  timbreLabel: document.querySelector('#timbre-label'),
  timbreDetail: document.querySelector('#timbre-detail'),
  matches: document.querySelector('#matches'),
  disclaimer: document.querySelector('#disclaimer'),
  startButton: document.querySelector('#start-button'),
  cancelButton: document.querySelector('#cancel-button'),
}

let selectedDuration = 8
let currentState = { phase: 'idle' }

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
  const busy = phase === 'capturing' || phase === 'analyzing'

  elements.startButton.disabled = busy
  elements.startButton.textContent = phase === 'analyzing' ? '识别中' : '开始识别'
  elements.cancelButton.hidden = phase !== 'capturing'
  elements.progressPanel.hidden = !busy
  elements.errorPanel.hidden = phase !== 'error'
  elements.resultPanel.hidden = phase !== 'result'

  if (busy) {
    const elapsed = Math.max(0, currentState.elapsedMs || 0)
    const duration = Math.max(1, currentState.durationMs || selectedDuration * 1000)
    const ratio = phase === 'analyzing' ? 1 : Math.min(1, elapsed / duration)
    elements.progressTitle.textContent =
      phase === 'analyzing' ? currentState.message || '正在识别音色' : currentState.message || '正在采集'
    elements.progressTime.textContent =
      phase === 'analyzing' ? '处理中' : `${(elapsed / 1000).toFixed(1)} / ${(duration / 1000).toFixed(1)} 秒`
    elements.progressBar.style.width = `${Math.round(ratio * 100)}%`
  }

  if (phase === 'error') {
    elements.errorMessage.textContent = currentState.message || '请稍后重试'
  }
  if (phase === 'result') {
    renderResult(currentState.result)
  }
}

function renderResult(result) {
  if (!result) return

  elements.resultBadge.textContent = result.matched ? '已匹配' : '未命中'
  elements.resultBadge.classList.toggle('matched', Boolean(result.matched))

  const features = result.features || {}
  elements.timbreLabel.textContent = features.label || '无稳定音色'
  const pitch = features.pitch_hz ? `基频 ${features.pitch_hz.toFixed(1)} Hz` : '基频未检出'
  const range =
    features.pitch_low_hz && features.pitch_high_hz
      ? ` · 音域 ${features.pitch_low_hz.toFixed(0)}-${features.pitch_high_hz.toFixed(0)} Hz`
      : ''
  elements.timbreDetail.textContent = `${pitch}${range}`

  elements.matches.replaceChildren()
  const matches = result.matches || []
  if (matches.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'empty'
    empty.textContent =
      result.note || '音色库为空，先到 Web 端创建至少一个自定义音色后可进行候选匹配。'
    elements.matches.append(empty)
  } else {
    matches.forEach((match, index) => {
      elements.matches.append(renderMatch(match, index))
    })
  }
  elements.disclaimer.textContent = result.disclaimer || ''
}

function renderMatch(match, index) {
  const item = document.createElement('div')
  item.className = 'match'
  const copy = document.createElement('div')
  const name = document.createElement('strong')
  name.textContent = `${index + 1}. ${match.name}`
  const meta = document.createElement('span')
  const kind = match.kind === 'builtin' ? '内置音色' : '音色库'
  const language = match.language ? ` · ${match.language}` : ''
  meta.textContent = `${kind}${language}`
  copy.append(name, meta)

  const score = document.createElement('div')
  score.className = 'match-score'
  score.textContent = `${Number(match.score || 0).toFixed(1)}%`
  item.append(copy, score)
  return item
}

async function loadBackendStatus() {
  const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE_URL,
  })
  const baseUrl = String(apiBaseUrl).replace(/\/+$/, '')
  try {
    const response = await fetch(`${baseUrl}/timbre/status`)
    const payload = await response.json()
    if (!response.ok) throw new Error(payload?.error?.message || `HTTP ${response.status}`)
    const stateText = payload.ready ? '模型已就绪' : `模型${payload.model_state}`
    elements.backendStatus.textContent = `${stateText} · 音色库 ${payload.voice_count} 个`
  } catch {
    elements.backendStatus.textContent = '后端未连接，请检查设置'
  }
}

elements.durationControl.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-duration]')
  if (!button || currentState.phase === 'capturing' || currentState.phase === 'analyzing') return
  setActiveDuration(Number(button.dataset.duration))
})

elements.startButton.addEventListener('click', async () => {
  const response = await sendMessage({
    type: 'TIMBRE_START',
    durationSeconds: selectedDuration,
  })
  if (!response?.ok) render({ phase: 'error', message: response?.message || '无法开始采集' })
})

elements.cancelButton.addEventListener('click', async () => {
  await sendMessage({ type: 'TIMBRE_CANCEL' })
  render({ phase: 'idle' })
})

elements.settingsButton.addEventListener('click', () => chrome.runtime.openOptionsPage())

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === 'TIMBRE_STATE') render(message.state)
})

async function initialize() {
  const response = await sendMessage({ type: 'TIMBRE_GET_STATE' })
  render(response?.state)
  void loadBackendStatus()
}

void initialize()
