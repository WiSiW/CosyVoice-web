import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { clearHistory, deleteAudio, fetchHistory } from '@/api/tts'
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

  function clearLocal(): void {
    items.value = []
    persist()
  }

  /**
   * 清空全部记录：先删服务端音频文件，再清本地列表。
   *
   * 注意不能只清本地 —— 列表会在下次 syncRemote() 时被服务端记录重新填满，
   * 那样"清空"看起来就是无效的（曾出现过这个问题）。
   */
  async function clearAll(): Promise<number> {
    const { deleted } = await clearHistory()
    clearLocal()
    return deleted
  }

  /**
   * 与服务端历史对齐：补齐缺失的记录，并剔除服务端已经不存在的记录。
   *
   * 只做"追加"是不够的 —— 服务端按 CV_MAX_HISTORY_FILES 自动清理、
   * 或在别处/别的浏览器清空过记录之后，本地会留下点不开的"僵尸记录"。
   */
  async function syncRemote(): Promise<void> {
    loading.value = true
    try {
      const remote = await fetchHistory(MAX_ITEMS)
      const remoteIds = new Set(remote.map((item) => item.audio_id))

      // remoteUrl 非空表示这条记录来自服务端；服务端没有它了就移除
      const kept = items.value.filter((item) => !item.remoteUrl || remoteIds.has(item.id))

      const known = new Set(kept.map((item) => item.id))
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

      if (missing.length || kept.length !== items.value.length) {
        items.value = [...kept, ...missing].slice(0, MAX_ITEMS)
        persist()
      }
    } finally {
      loading.value = false
    }
  }

  return { items, loading, count, add, remove, removeRemote, clearLocal, clearAll, syncRemote }
})
