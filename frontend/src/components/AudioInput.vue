<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import AudioPlayer from '@/components/AudioPlayer.vue'
import { useAudioRecorder } from '@/composables/useAudioRecorder'
import type { PreparedAudio } from '@/types'
import { prepareAudio } from '@/utils/audio'
import { formatDuration } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    modelValue: PreparedAudio | null
    label?: string
    hint?: string
    maxSeconds?: number
    accept?: string
  }>(),
  {
    label: '参考音频',
    hint: '建议 3~30 秒清晰人声，支持 WAV / MP3 / M4A / FLAC',
    maxSeconds: 30,
    accept: 'audio/*,.wav,.mp3,.m4a,.flac,.ogg',
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: PreparedAudio | null] }>()

const tab = ref<'upload' | 'record'>('upload')
const busy = ref(false)
const errorText = ref('')
const dragActive = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

const recorder = useAudioRecorder(props.maxSeconds)
const hasAudio = computed(() => Boolean(props.modelValue))

watch(
  () => recorder.error.value,
  (value) => {
    if (value) errorText.value = value
  },
)

async function ingest(blob: Blob, filename: string, source: 'upload' | 'record'): Promise<void> {
  busy.value = true
  errorText.value = ''
  try {
    const prepared = await prepareAudio(blob, filename)
    if (prepared.duration > props.maxSeconds + 0.5) {
      throw new Error(`音频时长 ${formatDuration(prepared.duration)} 超出上限 ${props.maxSeconds} 秒`)
    }
    prepared.source = source
    if (props.modelValue?.url) URL.revokeObjectURL(props.modelValue.url)
    emit('update:modelValue', prepared)
  } catch (error) {
    errorText.value = errorMessage(error)
  } finally {
    busy.value = false
  }
}

function onPick(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void ingest(file, file.name, 'upload')
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragActive.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void ingest(file, file.name, 'upload')
}

async function toggleRecord(): Promise<void> {
  errorText.value = ''
  if (recorder.recording.value) {
    const blob = await recorder.stop()
    if (blob) await ingest(blob, 'recording.webm', 'record')
    return
  }
  try {
    await recorder.start()
  } catch (error) {
    errorText.value = errorMessage(error)
  }
}

function clear(): void {
  if (props.modelValue?.url) URL.revokeObjectURL(props.modelValue.url)
  emit('update:modelValue', null)
}
</script>

<template>
  <div class="audio-input">
    <div class="head">
      <span class="label">{{ label }}</span>
      <div class="tabs">
        <button type="button" :class="{ active: tab === 'upload' }" @click="tab = 'upload'">上传文件</button>
        <button type="button" :class="{ active: tab === 'record' }" @click="tab = 'record'">麦克风录制</button>
      </div>
    </div>

    <div v-if="hasAudio && modelValue" class="preview">
      <AudioPlayer
        :src="modelValue.url"
        :title="`${modelValue.source === 'record' ? '录制音频' : modelValue.file.name} · ${formatDuration(modelValue.duration)}`"
        :download-name="modelValue.file.name"
      />
      <button class="btn danger sm" type="button" @click="clear">移除</button>
    </div>

    <template v-else>
      <div
        v-if="tab === 'upload'"
        class="dropzone"
        :class="{ active: dragActive, busy }"
        role="button"
        tabindex="0"
        @click="inputRef?.click()"
        @keydown.enter="inputRef?.click()"
        @dragover.prevent="dragActive = true"
        @dragleave.prevent="dragActive = false"
        @drop.prevent="onDrop"
      >
        <input ref="inputRef" class="hidden-input" type="file" :accept="accept" @change="onPick" />
        <span class="icon">{{ busy ? '⏳' : '📁' }}</span>
        <strong>{{ busy ? '正在转码为 16kHz WAV…' : '点击选择音频，或拖拽文件到此处' }}</strong>
        <span class="dim">{{ hint }}</span>
      </div>

      <div v-else class="recorder">
        <button
          class="rec-btn"
          :class="{ recording: recorder.recording.value }"
          type="button"
          @click="toggleRecord"
        >
          <span class="dot" />
          {{ recorder.recording.value ? `停止录制 ${recorder.seconds.value.toFixed(1)}s` : '开始录音' }}
        </button>
        <span class="dim">
          最长 {{ maxSeconds }} 秒；录制完成后会自动转码为 16kHz 单声道 WAV 并上传。
        </span>
      </div>
    </template>

    <p v-if="errorText" class="error">{{ errorText }}</p>
  </div>
</template>

<style scoped>
.audio-input {
  display: block;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}

.label {
  font-size: 13px;
  color: var(--text-muted);
  font-weight: 500;
}

.tabs {
  display: flex;
  gap: 4px;
}

.tabs button {
  border: none;
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  font-family: inherit;
  padding: 4px 9px;
  border-radius: 999px;
  cursor: pointer;
}

.tabs button.active {
  background: var(--accent-soft);
  color: var(--accent);
}

.dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  text-align: center;
  padding: 26px 16px;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  cursor: pointer;
  transition: border-color var(--transition), background var(--transition);
}

.dropzone:hover,
.dropzone.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.dropzone.busy {
  pointer-events: none;
  opacity: 0.75;
}

.dropzone .icon {
  font-size: 22px;
}

.dropzone strong {
  font-size: 13.5px;
  font-weight: 500;
}

.hidden-input {
  display: none;
}

.recorder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 22px 16px;
  border: 1.5px dashed var(--border-strong);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  text-align: center;
}

.rec-btn {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  border: 1px solid var(--border-strong);
  background: var(--bg-panel);
  color: var(--text);
  padding: 10px 20px;
  border-radius: 999px;
  font-size: 13.5px;
  font-family: inherit;
  cursor: pointer;
}

.rec-btn .dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--danger);
}

.rec-btn.recording {
  border-color: var(--danger);
  color: var(--danger);
}

.rec-btn.recording .dot {
  animation: pulse 1s infinite;
}

.preview {
  display: flex;
  align-items: center;
  gap: 10px;
}

.preview > :first-child {
  flex: 1;
  min-width: 0;
}

.btn.sm {
  padding: 7px 12px;
  font-size: 12px;
}

.error {
  margin: 8px 0 0;
  font-size: 12.5px;
  color: var(--danger);
}
</style>
