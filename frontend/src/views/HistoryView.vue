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
const clearing = ref(false)

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

async function clearAll(): Promise<void> {
  const total = history.items.length
  if (
    !window.confirm(
      `将删除服务端全部生成记录与本地列表（当前 ${total} 条），音频文件会一并删除且不可恢复。确定继续吗？`,
    )
  ) {
    return
  }
  clearing.value = true
  try {
    const deleted = await history.clearAll()
    toast.success(deleted ? `已清空 ${deleted} 条记录` : '没有需要清理的记录')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    clearing.value = false
  }
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>生成记录</h1>
      <p>
        「清空记录」会同时删除服务端音频文件与本地列表；服务端默认只保留最近若干条，
        可通过后端 <code class="mono">CV_MAX_HISTORY_FILES</code> 调整。
      </p>
    </div>
    <div class="inline">
      <button class="btn ghost" type="button" :disabled="syncing" @click="sync">
        <span v-if="syncing" class="spinner" />
        同步服务端记录
      </button>
      <button class="btn danger" type="button" :disabled="clearing || !history.items.length" @click="clearAll">
        <span v-if="clearing" class="spinner" />
        清空记录
      </button>
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
