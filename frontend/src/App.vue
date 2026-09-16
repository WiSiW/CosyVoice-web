<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView } from 'vue-router'

import { errorMessage } from '@/api/client'
import AppSidebar from '@/components/AppSidebar.vue'
import AppTopbar from '@/components/AppTopbar.vue'
import ToastHost from '@/components/ToastHost.vue'
import { useToast } from '@/composables/useToast'
import { useSystemStore } from '@/stores/system'
import { useVoiceStore } from '@/stores/voices'

const system = useSystemStore()
const voices = useVoiceStore()
const toast = useToast()

onMounted(async () => {
  try {
    await system.refresh()
    await Promise.all([voices.refresh(), voices.loadLanguages()])
  } catch (error) {
    toast.error(`初始化失败：${errorMessage(error)}`)
  }
})
</script>

<template>
  <div class="app-shell">
    <AppSidebar />

    <div class="app-main">
      <AppTopbar />

      <div v-if="!system.online" class="offline-bar">
        <div class="alert error">
          无法连接后端服务（{{ system.error || '网络错误' }}）。请在「设置」中确认 API 地址，并确保后端已启动：
          <code class="mono">uvicorn app.main:app --port 8000</code>
          <button class="btn ghost" type="button" @click="system.refresh()">重试</button>
        </div>
      </div>

      <main class="app-content">
        <RouterView v-slot="{ Component }">
          <component :is="Component" />
        </RouterView>
      </main>
    </div>

    <ToastHost />
  </div>
</template>

<style scoped>
.offline-bar {
  padding: 16px 32px 0;
}

.offline-bar .alert {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 0;
}

.offline-bar code {
  background: rgba(0, 0, 0, 0.25);
  padding: 2px 6px;
  border-radius: 6px;
}

@media (max-width: 860px) {
  .app-shell {
    flex-direction: column;
  }

  .offline-bar {
    padding: 12px 16px 0;
  }
}
</style>
