<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import StatusPill from '@/components/StatusPill.vue'
import { apiBaseUrl } from '@/api/runtime'
import { useSettingsStore } from '@/stores/settings'
import { useSystemStore } from '@/stores/system'

const route = useRoute()
const system = useSystemStore()
const settings = useSettingsStore()

const title = computed(() => (route.meta.title as string | undefined) ?? '控制台')
const endpointLabel = computed(() => apiBaseUrl.value || '同源 / 开发代理')

function toggleTheme(): void {
  settings.state.theme = settings.state.theme === 'dark' ? 'light' : 'dark'
}
</script>

<template>
  <header class="topbar">
    <div class="left">
      <span class="crumb">{{ title }}</span>
      <span class="dim mono endpoint" :title="`当前 API 地址：${endpointLabel}`">{{ endpointLabel }}</span>
    </div>

    <div class="right">
      <button class="btn ghost" type="button" :disabled="system.loading" @click="system.refresh()">
        <span v-if="system.loading" class="spinner" />
        <span v-else>↻</span>
        刷新状态
      </button>
      <StatusPill :model="system.model" />
      <button class="btn ghost" type="button" :title="`切换到${settings.state.theme === 'dark' ? '浅色' : '深色'}主题`" @click="toggleTheme">
        {{ settings.state.theme === 'dark' ? '☀️' : '🌙' }}
      </button>
    </div>
  </header>
</template>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 32px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(12px);
  position: sticky;
  top: 0;
  z-index: 20;
}

.left {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.crumb {
  font-size: 15px;
  font-weight: 600;
}

.endpoint {
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.right {
  display: flex;
  align-items: center;
  gap: 10px;
}

@media (max-width: 860px) {
  .topbar {
    padding: 10px 14px;
  }

  .endpoint {
    display: none;
  }
}
</style>
