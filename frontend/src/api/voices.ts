import type { Voice, VoiceUpdatePayload } from '@/types'

import { del, get, patch, post } from './client'

export interface CreateVoicePayload {
  name: string
  audio: Blob
  filename: string
  promptText?: string
  description?: string
  language?: string
  source?: 'upload' | 'record'
  autoRegister?: boolean
}

export function fetchVoices(): Promise<Voice[]> {
  return get('/voices')
}

export function fetchLanguages(): Promise<string[]> {
  return get('/voices/languages')
}

export function createVoice(payload: CreateVoicePayload): Promise<Voice> {
  const form = new FormData()
  form.append('name', payload.name)
  form.append('audio', payload.audio, payload.filename)
  form.append('prompt_text', payload.promptText ?? '')
  form.append('description', payload.description ?? '')
  form.append('language', payload.language ?? '中文')
  form.append('source', payload.source ?? 'upload')
  form.append('auto_register', String(payload.autoRegister ?? false))
  return post('/voices', form, { timeout: 300_000 })
}

export function updateVoice(id: string, payload: VoiceUpdatePayload): Promise<Voice> {
  return patch(`/voices/${id}`, payload)
}

export function registerVoice(id: string): Promise<Voice> {
  return post(`/voices/${id}/register`)
}

export function deleteVoice(id: string): Promise<void> {
  return del(`/voices/${id}`)
}

export function voiceAudioUrl(id: string): string {
  return `/api/v1/voices/${id}/audio`
}
