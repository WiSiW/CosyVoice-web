import type { ModeSpec, ModelStatus, SystemInfo } from '@/types'

import { get, post } from './client'

export function fetchHealth(): Promise<{ status: string; model_state: string }> {
  return get('/health', { timeout: 10_000 })
}

export function fetchSystemInfo(): Promise<SystemInfo> {
  return get('/system/info')
}

export function fetchModes(): Promise<ModeSpec[]> {
  return get('/system/modes')
}

export function loadModel(force = false): Promise<ModelStatus> {
  return post(`/system/load?force=${force ? 'true' : 'false'}`, undefined, { timeout: 30 * 60_000 })
}

export function unloadModel(): Promise<ModelStatus> {
  return post('/system/unload')
}
