<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import StatusPill from '@/components/StatusPill.vue'
import { useSystemStore } from '@/stores/system'

const route = useRoute()
const system = useSystemStore()

const links = [
  { name: 'synthesis', path: '/', label: '语音合成', icon: '🎙️' },
  { name: 'voices', path: '/voices', label: '音色库', icon: '🎧' },
  { name: 'history', path: '/history', label: '生成记录', icon: '🗂️' },
  { name: 'settings', path: '/settings', label: '设置', icon: '⚙️' },
]

const sampleRate = computed(() => system.model?.sample_rate)
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <span class="logo">🎙️</span>
      <div>
        <strong>CosyVoice</strong>
        <span class="dim">语音合成控制台</span>
      </div>
    </div>

    <nav class="nav">
      <RouterLink
        v-for="link in links"
        :key="link.name"
        :to="link.path"
        class="nav-item"
        :class="{ active: route.path === link.path }"
      >
        <span class="icon">{{ link.icon }}</span>
        {{ link.label }}
      </RouterLink>
    </nav>

    <div class="footer">
      <StatusPill :model="system.model" />
      <div class="dim">
        <div>采样率：{{ sampleRate ? `${sampleRate} Hz` : '-' }}</div>
        <div>音色数：{{ system.speakers.length }}</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
  flex: none;
  background: var(--bg-elevated);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 4px 8px 20px;
}

.brand .logo {
  font-size: 22px;
}

.brand strong {
  display: block;
  font-size: 15px;
  letter-spacing: 0.02em;
}

.brand .dim {
  font-size: 11px;
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  color: var(--text-muted);
  font-size: 13.5px;
  transition: background var(--transition), color var(--transition);
}

.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text);
}

.nav-item.active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.footer {
  margin-top: auto;
  padding: 14px 8px 4px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (max-width: 860px) {
  .sidebar {
    width: 100%;
    height: auto;
    position: static;
    flex-direction: row;
    align-items: center;
    gap: 14px;
    padding: 10px 14px;
    border-right: none;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }

  .brand {
    padding: 0;
  }

  .brand .dim {
    display: none;
  }

  .nav {
    flex-direction: row;
    gap: 2px;
  }

  .nav-item {
    white-space: nowrap;
    padding: 8px 10px;
  }

  .footer {
    display: none;
  }
}
</style>
