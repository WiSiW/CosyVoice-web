import { defineStore } from 'pinia'
import { computed, reactive, watch } from 'vue'

import { apiBaseUrl, setApiBaseUrl } from '@/api/runtime'
import type { ModeId } from '@/types'

const STORAGE_KEY = 'cosyvoice.settings'

export interface PersistedSettings {
  defaultMode: ModeId
  streaming: boolean
  autoRegister: boolean
  theme: 'dark' | 'light'
  speed: number
  textFrontend: boolean
}

const DEFAULTS: PersistedSettings = {
  defaultMode: 'zero_shot',
  streaming: true,
  autoRegister: true,
  theme: 'dark',
  speed: 1,
  textFrontend: true,
}

function load(): PersistedSettings {
  if (typeof localStorage === 'undefined') return { ...DEFAULTS }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULTS, ...(JSON.parse(raw) as Partial<PersistedSettings>) } : { ...DEFAULTS }
  } catch {
    return { ...DEFAULTS }
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const stored = load()
  const state = reactive<PersistedSettings>({ ...stored })

  const apiBase = computed({
    get: () => apiBaseUrl.value,
    set: (value: string) => setApiBaseUrl(value),
  })

  function applyTheme(): void {
    if (typeof document === 'undefined') return
    document.documentElement.dataset.theme = state.theme
  }

  function persist(): void {
    if (typeof localStorage === 'undefined') return
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  }

  function reset(): void {
    Object.assign(state, DEFAULTS)
    applyTheme()
    persist()
  }

  watch(state, () => {
    persist()
    applyTheme()
  }, { deep: true })

  applyTheme()

  return { state, apiBase, applyTheme, reset }
})
