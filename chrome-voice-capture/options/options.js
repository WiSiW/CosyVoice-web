const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'

const form = document.querySelector('#settings-form')
const input = document.querySelector('#api-base-url')
const testButton = document.querySelector('#test-button')
const notice = document.querySelector('#notice')

function normalizeBaseUrl(value) {
  const parsed = new URL(String(value).trim())
  parsed.hash = ''
  parsed.search = ''
  return parsed.toString().replace(/\/+$/, '')
}

function showNotice(message, isError = false) {
  notice.hidden = false
  notice.textContent = message
  notice.classList.toggle('error', isError)
}

async function ensureHostPermission(baseUrl) {
  const parsed = new URL(baseUrl)
  const originPattern = `${parsed.protocol}//${parsed.hostname}/*`
  const granted = await chrome.permissions.contains({ origins: [originPattern] })
  if (granted) return
  const requested = await chrome.permissions.request({ origins: [originPattern] })
  if (!requested) throw new Error('未授权访问该后端地址')
}

async function testConnection(baseUrl) {
  const response = await fetch(`${baseUrl}/timbre/status`)
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.error?.message || `后端返回 ${response.status}`)
  return payload
}

async function initialize() {
  const { apiBaseUrl = DEFAULT_API_BASE_URL } = await chrome.storage.sync.get({
    apiBaseUrl: DEFAULT_API_BASE_URL,
  })
  input.value = apiBaseUrl
}

form.addEventListener('submit', async (event) => {
  event.preventDefault()
  try {
    const baseUrl = normalizeBaseUrl(input.value)
    await ensureHostPermission(baseUrl)
    await chrome.storage.sync.set({ apiBaseUrl: baseUrl })
    input.value = baseUrl
    showNotice('设置已保存')
  } catch (error) {
    showNotice(error instanceof Error ? error.message : String(error), true)
  }
})

testButton.addEventListener('click', async () => {
  try {
    const baseUrl = normalizeBaseUrl(input.value)
    await ensureHostPermission(baseUrl)
    const payload = await testConnection(baseUrl)
    const state = payload.ready ? '模型已就绪' : `模型状态：${payload.model_state}`
    showNotice(`${state}，音色库共 ${payload.voice_count} 个音色`)
  } catch (error) {
    showNotice(error instanceof Error ? error.message : String(error), true)
  }
})

void initialize()
