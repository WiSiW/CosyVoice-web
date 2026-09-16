import { ref } from 'vue'

/** 运行时 API 地址配置：支持在设置页热切换并持久化到 localStorage。 */
const STORAGE_KEY = 'cosyvoice.apiBaseUrl'

export const API_PREFIX = import.meta.env.VITE_API_PREFIX || '/api/v1'

export function normalizeBaseUrl(value: string): string {
  return (value || '').trim().replace(/\/+$/, '')
}

const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null

export const apiBaseUrl = ref<string>(normalizeBaseUrl(stored ?? import.meta.env.VITE_API_BASE_URL ?? ''))

export function setApiBaseUrl(value: string): void {
  apiBaseUrl.value = normalizeBaseUrl(value)
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(STORAGE_KEY, apiBaseUrl.value)
  }
}

/** 拼接完整接口地址，例如 /api/v1/health */
export function apiUrl(path: string): string {
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${apiBaseUrl.value}${API_PREFIX}${suffix}`
}

/** 把后端返回的相对音频地址转换为可直接播放的地址 */
export function resolveMediaUrl(url?: string | null): string {
  if (!url) return ''
  if (/^https?:\/\//i.test(url) || url.startsWith('blob:') || url.startsWith('data:')) return url
  return `${apiBaseUrl.value}${url}`
}
