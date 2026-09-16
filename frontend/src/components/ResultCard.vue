<script setup lang="ts">
import { computed } from 'vue'

import AudioPlayer from '@/components/AudioPlayer.vue'
import { useToast } from '@/composables/useToast'
import type { GenerationItem } from '@/types'
import { formatDuration, formatRelative } from '@/utils/format'

const props = defineProps<{ item: GenerationItem }>()
const emit = defineEmits<{ remove: [id: string] }>()

const toast = useToast()

const src = computed(() => props.item.localUrl || props.item.remoteUrl || '')
const downloadName = computed(() => `${props.item.modeLabel}-${props.item.id}.wav`)

async function copyText(): Promise<void> {
  if (!props.item.text) return
  try {
    await navigator.clipboard.writeText(props.item.text)
    toast.success('文本已复制到剪贴板')
  } catch {
    toast.error('复制失败，请手动选择文本')
  }
}
</script>

<template>
  <article class="result">
    <header>
      <div class="meta">
        <span class="tag">{{ item.modeLabel }}</span>
        <span class="dim">{{ item.voiceLabel }}</span>
        <span v-if="item.duration" class="dim">· {{ formatDuration(item.duration) }}</span>
        <span v-if="item.rtf" class="dim">· RTF {{ item.rtf.toFixed(2) }}</span>
        <span class="dim">· {{ formatRelative(item.createdAt) }}</span>
      </div>
      <div class="actions">
        <button v-if="item.text" class="btn ghost sm" type="button" title="复制文本" @click="copyText">复制</button>
        <button class="btn danger sm" type="button" title="删除记录" @click="emit('remove', item.id)">删除</button>
      </div>
    </header>

    <p v-if="item.text" class="text">{{ item.text }}</p>

    <AudioPlayer v-if="src" :src="src" :download-name="downloadName" :title="item.voiceLabel" />
    <p v-else class="dim">音频已不可用（服务端文件可能已被清理）</p>
  </article>
</template>

<style scoped>
.result {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px;
  background: var(--bg-panel);
}

.result + .result {
  margin-top: 12px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  min-width: 0;
}

.actions {
  display: flex;
  gap: 4px;
}

.text {
  margin: 0 0 10px;
  font-size: 13.5px;
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 130px;
  overflow: auto;
}

.btn.sm {
  padding: 5px 10px;
  font-size: 12px;
}
</style>
