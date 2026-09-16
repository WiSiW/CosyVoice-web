import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { deleteAudio, fetchHistory } from '@/api/tts'
import type { GenerationItem } from '@/types'

const STORAGE_KEY = 'cosyvoice.history'
const MAX_ITEMS = 60

function load(): GenerationItem[] {
  if (typeof localStorage === 'undefined') return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as GenerationItem[]) : []
  } catch {
    return []
  }
}

export const useHistoryStore = defineStore('history', () => {
  const items = ref<GenerationItem[]>(load())
  const loading = ref(false)

  const count = computed(() => items.value.length)

  function persist(): void {
    if (typeof localStorage === 'undefined') return
    const slim = items.value.slice(0, MAX_ITEMS).map(({ localUrl: _localUrl, ...rest }) => rest)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
  }

  function add(item: GenerationItem): void {
    items.value = [item, ...items.value].slice(0, MAX_ITEMS)
    persist()
  }

  function remove(id: string): void {
    items.value = items.value.filter((item) => item.id !== id)
    persist()
  }

  async function removeRemote(id: string): Promise<void> {
    try {
      await deleteAudio(id)
    } finally {
      remove(id)
    }
  }

  function clear(): void {
    items.value = []
    persist()
  }

  /** 拉取服务端历史，补齐本地没有的记录 */
  async function syncRemote(): Promise<void> {
    loading.value = true
    try {
      const remote = await fetchHistory(MAX_ITEMS)
      const known = new Set(items.value.map((item) => item.id))
      const missing: GenerationItem[] = remote
        .filter((item) => !known.has(item.audio_id))
        .map((item) => ({
          id: item.audio_id,
          mode: 'unknown',
          modeLabel: '历史记录',
          text: item.filename,
          voiceLabel: '-',
          duration: 0,
          createdAt: item.created_at,
          remoteUrl: item.url,
        }))
      if (missing.length) {
        items.value = [...items.value, ...missing].slice(0, MAX_ITEMS)
        persist()
      }
    } finally {
      loading.value = false
    }
  }

  return { items, loading, count, add, remove, removeRemote, clear, syncRemote }
})
