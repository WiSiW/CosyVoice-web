<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { errorMessage } from '@/api/client'
import ResultCard from '@/components/ResultCard.vue'
import { useToast } from '@/composables/useToast'
import { useHistoryStore } from '@/stores/history'
import { formatDateTime } from '@/utils/format'

const history = useHistoryStore()
const toast = useToast()

const keyword = ref('')
const syncing = ref(false)

const filtered = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return history.items
  return history.items.filter((item) =>
    [item.text, item.modeLabel, item.voiceLabel].some((field) => field.toLowerCase().includes(query)),
  )
})

onMounted(() => {
  void sync()
})

async function sync(): Promise<void> {
  syncing.value = true
  try {
    await history.syncRemote()
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    syncing.value = false
  }
}

async function remove(id: string): Promise<void> {
  try {
    await history.removeRemote(id)
    toast.success('已删除')
  } catch (error) {
    history.remove(id)
    toast.error(errorMessage(error))
  }
}

function clearLocal(): void {
  if (!window.confirm('仅清除本地记录列表，服务端音频文件仍会保留，确定继续吗？')) return
  history.clear()
  toast.success('本地记录已清空')
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>生成记录</h1>
      <p>本地记录保存在浏览器中；服务端音频默认保留最近若干条，可在后端配置 <code class="mono">CV_MAX_HISTORY_FILES</code>。</p>
    </div>
    <div class="inline">
      <button class="btn ghost" type="button" :disabled="syncing" @click="sync">
        <span v-if="syncing" class="spinner" />
        同步服务端记录
      </button>
      <button class="btn ghost" type="button" :disabled="!history.items.length" @click="clearLocal">清空本地</button>
    </div>
  </div>

  <div class="card">
    <div class="card-title">
      <h2>记录列表（{{ filtered.length }} / {{ history.items.length }}）</h2>
      <input v-model="keyword" class="search" type="text" placeholder="搜索文本 / 模式 / 音色" />
    </div>

    <div v-if="!history.items.length" class="empty">
      <span class="icon">🗂️</span>
      暂无生成记录，去「语音合成」页面生成第一条音频吧。
    </div>

    <template v-else-if="!filtered.length">
      <div class="empty">没有匹配「{{ keyword }}」的记录</div>
    </template>

    <template v-else>
      <p class="dim list-hint">最近一次生成：{{ formatDateTime(filtered[0].createdAt) }}</p>
      <ResultCard v-for="item in filtered" :key="item.id" :item="item" @remove="remove" />
    </template>
  </div>
</template>

<style scoped>
.search {
  max-width: 280px;
}

.list-hint {
  margin: 0 0 12px;
}
</style>
