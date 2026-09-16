<script setup lang="ts">
import type { ModeId, ModeSpec } from '@/types'

defineProps<{ modes: ModeSpec[]; modelValue: ModeId }>()
const emit = defineEmits<{ 'update:modelValue': [value: ModeId] }>()
</script>

<template>
  <div class="tabs" role="tablist">
    <button
      v-for="mode in modes"
      :key="mode.id"
      type="button"
      role="tab"
      class="tab"
      :class="{ active: mode.id === modelValue, unavailable: !mode.available }"
      :disabled="!mode.available"
      :aria-selected="mode.id === modelValue"
      :title="mode.note || mode.description"
      @click="emit('update:modelValue', mode.id)"
    >
      {{ mode.label }}
    </button>
  </div>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: 6px;
  padding: 5px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow-x: auto;
}

.tab {
  flex: none;
  border: none;
  background: transparent;
  color: var(--text-muted);
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--transition), color var(--transition);
}

.tab:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text);
}

.tab.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.tab.unavailable {
  opacity: 0.42;
  cursor: not-allowed;
  text-decoration: line-through;
}
</style>
