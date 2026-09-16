<script setup lang="ts">
import { computed, ref } from 'vue'

import { errorMessage } from '@/api/client'
import { apiUrl } from '@/api/runtime'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'
import { useSystemStore } from '@/stores/system'
import { useVoiceStore } from '@/stores/voices'
import { formatDateTime } from '@/utils/format'

const settings = useSettingsStore()
const system = useSystemStore()
const voices = useVoiceStore()
const toast = useToast()

const endpointInput = ref(settings.apiBase)
const testing = ref(false)
const testOk = ref<boolean | null>(null)

const model = computed(() => system.model)
const stateLabel = computed(() => {
  const map: Record<string, string> = {
    unloaded: '未加载',
    loading: '加载中',
    ready: '已就绪',
    error: '加载失败',
    unknown: '未知',
  }
  return map[model.value?.state ?? 'unknown'] ?? model.value?.state ?? '未知'
})

const resolvedEndpoint = computed(() => apiUrl('/health'))

async function runTest(): Promise<void> {
  testing.value = true
  testOk.value = null
  try {
    await system.refresh()
    testOk.value = true
    toast.success('后端连接正常')
  } catch (error) {
    testOk.value = false
    toast.error(errorMessage(error))
  } finally {
    testing.value = false
  }
}

function saveEndpoint(): void {
  settings.apiBase = endpointInput.value
  toast.info('API 地址已保存，正在重新检测…')
  void runTest()
}

async function loadModel(): Promise<void> {
  try {
    await system.load(false)
    await voices.refresh()
    toast.success('模型加载完成')
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

async function unloadModel(): Promise<void> {
  try {
    await system.unload()
    toast.info('模型已卸载')
  } catch (error) {
    toast.error(errorMessage(error))
  }
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>设置</h1>
      <p>配置前端访问的后端地址、默认合成参数，以及查看模型运行状态。</p>
    </div>
  </div>

  <div class="grid two">
    <section class="card">
      <div class="card-title">
        <h2>连接与默认参数</h2>
      </div>

      <div class="field">
        <label for="endpoint">后端 API 地址</label>
        <div class="inline">
          <input
            id="endpoint"
            v-model="endpointInput"
            type="text"
            placeholder="留空表示使用同源 / 开发代理，例如 http://127.0.0.1:8000"
          />
          <button class="btn" type="button" @click="saveEndpoint">保存并测试</button>
        </div>
        <span class="sub">
          当前请求地址：<code class="mono">{{ resolvedEndpoint }}</code>
        </span>
      </div>

      <div class="row">
        <div class="field">
          <label for="default-mode">默认合成模式</label>
          <select id="default-mode" v-model="settings.state.defaultMode">
            <option v-for="mode in system.modes" :key="mode.id" :value="mode.id" :disabled="!mode.available">
              {{ mode.label }}
            </option>
          </select>
        </div>

        <div class="field">
          <label for="default-speed">默认语速（{{ settings.state.speed.toFixed(2) }}x）</label>
          <input
            id="default-speed"
            v-model.number="settings.state.speed"
            type="range"
            :min="system.limits.speed.min"
            :max="system.limits.speed.max"
            step="0.05"
          />
        </div>
      </div>

      <div class="field">
        <label>默认开关</label>
        <div class="switches">
          <label class="checkbox">
            <input v-model="settings.state.streaming" type="checkbox" />
            流式合成（边生成边播放，首包延迟更低）
          </label>
          <label class="checkbox">
            <input v-model="settings.state.textFrontend" type="checkbox" />
            文本正则化（数字、符号、特殊格式自动规范化）
          </label>
          <label class="checkbox">
            <input v-model="settings.state.autoRegister" type="checkbox" />
            新建音色后自动注册到推理运行时
          </label>
          <label class="checkbox">
            <input v-model="settings.state.theme" type="checkbox" true-value="light" false-value="dark" />
            使用浅色主题
          </label>
        </div>
      </div>

      <div class="inline">
        <button class="btn ghost" type="button" @click="settings.reset()">恢复默认设置</button>
        <button class="btn ghost" type="button" :disabled="testing" @click="runTest">
          <span v-if="testing" class="spinner" />
          重新检测连接
        </button>
        <span v-if="testOk === true" class="tag success">连接正常</span>
        <span v-if="testOk === false" class="tag danger">连接失败</span>
      </div>
    </section>

    <section>
      <div class="card">
        <div class="card-title">
          <h2>模型状态</h2>
          <span class="tag" :class="model?.state === 'ready' ? 'success' : model?.state === 'error' ? 'danger' : 'muted'">
            {{ stateLabel }}
          </span>
        </div>

        <dl class="kv">
          <div><dt>后端类型</dt><dd>{{ model?.kind ?? '-' }}</dd></div>
          <div><dt>模型族</dt><dd>{{ model?.family ?? '-' }}</dd></div>
          <div><dt>采样率</dt><dd>{{ model?.sample_rate ? `${model.sample_rate} Hz` : '-' }}</dd></div>
          <div><dt>模型目录</dt><dd class="mono break">{{ model?.model_dir ?? '-' }}</dd></div>
          <div><dt>来源</dt><dd>{{ model?.model_source === 'local' ? '本地目录' : 'ModelScope 仓库' }}</dd></div>
          <div><dt>加载耗时</dt><dd>{{ model?.load_seconds ? `${model.load_seconds}s` : '-' }}</dd></div>
          <div><dt>加载时间</dt><dd>{{ model?.loaded_at ? formatDateTime(model.loaded_at) : '-' }}</dd></div>
          <div><dt>等待队列</dt><dd>{{ model?.inference_queue ?? 0 }}</dd></div>
        </dl>

        <div v-if="model?.mock" class="alert warning">
          当前运行在 Mock 模式：不会加载真实权重，返回的是模拟音频。取消后端 <code class="mono">CV_MOCK=true</code>
          并配置模型目录后即可使用真实推理。
        </div>
        <div v-if="model?.error" class="alert error">{{ model.error }}</div>

        <div class="inline">
          <button class="btn primary" type="button" :disabled="system.loadingModel" @click="loadModel">
            <span v-if="system.loadingModel" class="spinner" />
            {{ system.loadingModel ? '加载中…' : model?.state === 'ready' ? '重新加载模型' : '加载模型' }}
          </button>
          <button class="btn ghost" type="button" :disabled="system.loadingModel || model?.state !== 'ready'" @click="unloadModel">
            卸载并释放显存
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h2>服务信息</h2>
        </div>
        <dl class="kv">
          <div><dt>服务名称</dt><dd>{{ system.info?.app ?? '-' }}</dd></div>
          <div><dt>版本</dt><dd>{{ system.info?.version ?? '-' }}</dd></div>
          <div><dt>内置音色</dt><dd>{{ system.speakers.length }} 个</dd></div>
          <div><dt>自定义音色</dt><dd>{{ voices.items.length }} 个</dd></div>
          <div><dt>文本上限</dt><dd>{{ system.limits.max_text_length }} 字</dd></div>
          <div><dt>参考音频</dt><dd>{{ system.limits.min_prompt_seconds }}~{{ system.limits.max_prompt_seconds }} 秒</dd></div>
          <div><dt>上传上限</dt><dd>{{ system.limits.max_upload_mb }} MB</dd></div>
        </dl>

        <div v-if="system.speakers.length" class="speakers">
          <span v-for="speaker in system.speakers" :key="speaker" class="tag muted">{{ speaker }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.switches {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.kv {
  margin: 0 0 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.kv > div {
  display: flex;
  gap: 12px;
  font-size: 13px;
}

.kv dt {
  width: 88px;
  flex: none;
  color: var(--text-dim);
}

.kv dd {
  margin: 0;
  flex: 1;
  min-width: 0;
}

.break {
  word-break: break-all;
}

.speakers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

code {
  background: var(--bg-hover);
  padding: 1px 5px;
  border-radius: 5px;
}
</style>
