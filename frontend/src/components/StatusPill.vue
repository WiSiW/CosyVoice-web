<script setup lang="ts">
import { computed } from 'vue'

import type { ModelStatus } from '@/types'

const props = defineProps<{ model: ModelStatus | null; compact?: boolean }>()

const label = computed(() => {
  const state = props.model?.state
  if (state === 'ready') return `${props.model?.family ?? '模型'} 就绪`
  if (state === 'loading') return '模型加载中'
  if (state === 'error') return '模型异常'
  return '模型未加载'
})

const tone = computed(() => {
  const state = props.model?.state
  if (state === 'ready') return 'ready'
  if (state === 'loading') return 'loading'
  if (state === 'error') return 'error'
  return 'idle'
})
</script>

<template>
  <span class="pill" :title="model?.error ?? model?.note ?? label">
    <i class="status-dot" :class="tone" />
    <template v-if="!compact">{{ label }}</template>
  </span>
</template>

<style scoped>
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
}
</style>
