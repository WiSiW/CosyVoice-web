import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchModes, fetchSystemInfo, loadModel, unloadModel } from '@/api/system'
import type { ModeSpec, SystemInfo } from '@/types'

export const useSystemStore = defineStore('system', () => {
  const info = ref<SystemInfo | null>(null)
  const modes = ref<ModeSpec[]>([])
  const loading = ref(false)
  const loadingModel = ref(false)
  const online = ref(false)
  const error = ref('')

  const model = computed(() => info.value?.model ?? null)
  const ready = computed(() => model.value?.state === 'ready')
  const speakers = computed(() => info.value?.speakers ?? [])
  const limits = computed(
    () =>
      info.value?.limits ?? {
        max_upload_mb: 30,
        max_prompt_seconds: 30,
        min_prompt_seconds: 0.5,
        max_text_length: 2000,
        speed: { min: 0.5, max: 2 },
      },
  )
  const availableModes = computed(() => modes.value.filter((item) => item.available))

  async function refresh(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const [systemInfo, modeList] = await Promise.all([fetchSystemInfo(), fetchModes()])
      info.value = systemInfo
      modes.value = modeList
      online.value = true
    } catch (err) {
      online.value = false
      error.value = errorMessage(err)
      throw err
    } finally {
      loading.value = false
    }
  }

  async function load(force = false): Promise<void> {
    loadingModel.value = true
    error.value = ''
    try {
      const status = await loadModel(force)
      if (info.value) info.value.model = status
      info.value = info.value ? { ...info.value, model: status } : info.value
      if (status.state === 'ready') {
        await refresh()
      }
    } catch (err) {
      error.value = errorMessage(err)
      throw err
    } finally {
      loadingModel.value = false
    }
  }

  async function unload(): Promise<void> {
    loadingModel.value = true
    try {
      const status = await unloadModel()
      if (info.value) info.value = { ...info.value, model: status }
    } finally {
      loadingModel.value = false
    }
  }

  return {
    info,
    modes,
    loading,
    loadingModel,
    online,
    error,
    model,
    ready,
    speakers,
    limits,
    availableModes,
    refresh,
    load,
    unload,
  }
})
