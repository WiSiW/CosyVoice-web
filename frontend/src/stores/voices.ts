import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createVoice,
  deleteVoice,
  fetchLanguages,
  fetchVoices,
  registerVoice,
  updateVoice,
} from '@/api/voices'
import type { CreateVoicePayload } from '@/api/voices'
import type { Voice, VoiceUpdatePayload } from '@/types'

export const useVoiceStore = defineStore('voices', () => {
  const items = ref<Voice[]>([])
  const languages = ref<string[]>(['中文'])
  const loading = ref(false)
  const error = ref('')

  const options = computed(() =>
    items.value.map((voice) => ({
      value: voice.id,
      label: voice.name,
      detail: `${voice.language} · ${voice.audio.duration.toFixed(1)}s · ${
        voice.registered ? '已加载' : '未加载'
      }`,
    })),
  )

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      items.value = await fetchVoices()
    } catch (err) {
      error.value = (err as Error).message
      throw err
    } finally {
      loading.value = false
    }
  }

  async function loadLanguages(): Promise<void> {
    try {
      languages.value = await fetchLanguages()
    } catch {
      /* 语言列表非关键路径，失败时保留默认值 */
    }
  }

  async function create(payload: CreateVoicePayload): Promise<Voice> {
    const voice = await createVoice(payload)
    items.value = [voice, ...items.value]
    return voice
  }

  async function update(id: string, payload: VoiceUpdatePayload): Promise<Voice> {
    const voice = await updateVoice(id, payload)
    items.value = items.value.map((item) => (item.id === id ? voice : item))
    return voice
  }

  async function register(id: string): Promise<Voice> {
    const voice = await registerVoice(id)
    items.value = items.value.map((item) => (item.id === id ? voice : item))
    return voice
  }

  async function remove(id: string): Promise<void> {
    await deleteVoice(id)
    items.value = items.value.filter((item) => item.id !== id)
  }

  function byId(id: string): Voice | undefined {
    return items.value.find((item) => item.id === id)
  }

  return { items, languages, loading, error, options, refresh, loadLanguages, create, update, register, remove, byId }
})
