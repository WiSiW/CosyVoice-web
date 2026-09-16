<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { resolveMediaUrl } from '@/api/runtime'

const props = defineProps<{
  src: string
  title?: string
  downloadName?: string
  speed?: number
}>()

const emit = defineEmits<{ ended: [] }>()

const audio = ref<HTMLAudioElement | null>(null)
const playing = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const rate = ref(props.speed ?? 1)
const failed = ref(false)

const resolvedSrc = computed(() => resolveMediaUrl(props.src))
const progress = computed(() => (duration.value ? (currentTime.value / duration.value) * 100 : 0))

function toggle(): void {
  const element = audio.value
  if (!element) return
  if (element.paused) {
    void element.play()
  } else {
    element.pause()
  }
}

function onSeek(event: Event): void {
  const element = audio.value
  if (!element || !duration.value) return
  const ratio = Number((event.target as HTMLInputElement).value) / 100
  element.currentTime = ratio * duration.value
  currentTime.value = element.currentTime
}

function onRateChange(event: Event): void {
  const value = Number((event.target as HTMLSelectElement).value)
  rate.value = value
  if (audio.value) audio.value.playbackRate = value
}

function onTimeUpdate(event: Event): void {
  currentTime.value = (event.target as HTMLAudioElement).currentTime
}

function onLoadedMetadata(event: Event): void {
  duration.value = (event.target as HTMLAudioElement).duration
}

function onEnded(): void {
  playing.value = false
  emit('ended')
}

function formatTime(value: number): string {
  if (!Number.isFinite(value)) return '0:00'
  const minutes = Math.floor(value / 60)
  const seconds = Math.floor(value % 60)
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

watch(
  () => props.src,
  () => {
    playing.value = false
    currentTime.value = 0
    duration.value = 0
    failed.value = false
  },
)

onBeforeUnmount(() => {
  audio.value?.pause()
})
</script>

<template>
  <div class="player" :class="{ failed }">
    <button class="play" type="button" :disabled="failed" :aria-label="playing ? '暂停' : '播放'" @click="toggle">
      {{ failed ? '⚠' : playing ? '❚❚' : '▶' }}
    </button>

    <div class="body">
      <div class="head">
        <span class="title">{{ title || '生成结果' }}</span>
        <span class="time mono">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
      </div>

      <input
        class="seek"
        type="range"
        min="0"
        max="100"
        step="0.1"
        :value="progress"
        :disabled="!duration"
        aria-label="播放进度"
        @input="onSeek"
      />
    </div>

    <select class="rate" :value="rate" aria-label="播放速度" @change="onRateChange">
      <option :value="0.75">0.75x</option>
      <option :value="1">1x</option>
      <option :value="1.25">1.25x</option>
      <option :value="1.5">1.5x</option>
      <option :value="2">2x</option>
    </select>

    <a v-if="downloadName" class="download" :href="resolvedSrc" :download="downloadName" title="下载音频">⬇</a>

    <audio
      ref="audio"
      :src="resolvedSrc"
      preload="metadata"
      @play="playing = true"
      @pause="playing = false"
      @timeupdate="onTimeUpdate"
      @loadedmetadata="onLoadedMetadata"
      @ended="onEnded"
      @error="failed = true"
    />
  </div>
</template>

<style scoped>
.player {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}

.player.failed {
  border-color: rgba(255, 107, 129, 0.45);
}

.play {
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  display: grid;
  place-items: center;
}

.play:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.body {
  flex: 1;
  min-width: 0;
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 2px;
}

.title {
  font-size: 12.5px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.time {
  color: var(--text-dim);
  flex: none;
}

.seek {
  width: 100%;
  margin: 0;
}

.rate {
  width: auto;
  flex: none;
  padding: 5px 6px;
  font-size: 12px;
}

.download {
  flex: none;
  font-size: 15px;
  color: var(--text-muted);
  padding: 4px 6px;
  border-radius: 6px;
}

.download:hover {
  background: var(--bg-hover);
  color: var(--accent);
}

audio {
  display: none;
}
</style>
