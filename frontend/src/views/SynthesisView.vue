<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { synthesize, type SynthesisPayload } from '@/api/tts'
import AudioInput from '@/components/AudioInput.vue'
import ModeTabs from '@/components/ModeTabs.vue'
import ResultCard from '@/components/ResultCard.vue'
import VoicePicker from '@/components/VoicePicker.vue'
import { usePcmStreamPlayer } from '@/composables/usePcmStreamPlayer'
import { useToast } from '@/composables/useToast'
import { useHistoryStore } from '@/stores/history'
import { useSettingsStore } from '@/stores/settings'
import { useSystemStore } from '@/stores/system'
import { useVoiceStore } from '@/stores/voices'
import type { GenerationItem, ModeField, ModeId, PreparedAudio } from '@/types'
import { formatDuration } from '@/utils/format'

const system = useSystemStore()
const voices = useVoiceStore()
const settings = useSettingsStore()
const history = useHistoryStore()
const toast = useToast()
const stream = usePcmStreamPlayer()

const form = reactive({
  mode: settings.state.defaultMode as ModeId,
  ttsText: '',
  speakerValue: system.speakers[0] ?? '',
  voiceValue: '',
  promptText: '',
  instructText: '',
  speed: settings.state.speed,
  seed: null as number | null,
  textFrontend: settings.state.textFrontend,
})

const promptAudio = ref<PreparedAudio | null>(null)
const sourceAudio = ref<PreparedAudio | null>(null)
// 「3s 极速复刻」上传新参考音频时，可同时把音色存进音色库
const saveVoice = ref(true)
const voiceName = ref('')
const formError = ref('')
const busy = ref(false)
const lastResult = ref<GenerationItem | null>(null)
let lastBlobUrl = ''

const samples = [
  '你好，我是通义生成式语音大模型，请问有什么可以帮您的吗？',
  '收到好友从远方寄来的生日礼物，那份意外的惊喜与深深的祝福让我心中充满了甜蜜的快乐。',
  '在面对挑战时，他展现了非凡的勇气与智慧，最终带领团队走出了困境。',
  'And then later on, fully acquiring that company, keeping management in line with the asset.',
]

const currentMode = computed(() => system.modes.find((item) => item.id === form.mode) ?? null)
const fields = computed<ModeField[]>(() => currentMode.value?.fields ?? [])
const needs = (field: ModeField): boolean => fields.value.includes(field)
const generating = computed(() => busy.value || stream.streaming.value)
const maxTextLength = computed(() => system.limits.max_text_length)
const useStream = computed(
  () => settings.state.streaming && (currentMode.value?.supports_stream ?? false) && form.mode !== 'vc',
)
const supportsVoiceLibrary = computed(() =>
  ['zero_shot', 'cross_lingual', 'instruct2'].includes(form.mode),
)
const showVoicePicker = computed(() => needs('speaker') || supportsVoiceLibrary.value)

const voiceLabel = computed(() => {
  if (form.voiceValue) return voices.byId(form.voiceValue)?.name ?? '自定义音色'
  if (form.speakerValue) return form.speakerValue
  if (promptAudio.value) return '上传的参考音频'
  return '-'
})

watch(
  () => system.speakers,
  (list) => {
    if (!form.speakerValue && list.length) form.speakerValue = list[0]
  },
  { immediate: true },
)

watch(
  () => form.mode,
  (mode) => {
    formError.value = ''
    settings.state.defaultMode = mode
    const spec = system.modes.find((item) => item.id === mode)
    if (spec && !spec.fields.includes('prompt_audio')) promptAudio.value = null
    if (spec && !spec.fields.includes('source_audio')) sourceAudio.value = null
    if (mode === 'vc') form.voiceValue = ''
    if (mode === 'instruct') {
      form.voiceValue = ''
      if (!form.speakerValue && system.speakers.length) form.speakerValue = system.speakers[0]
    }
  },
)

watch(
  () => system.modes,
  (list) => {
    const current = list.find((item) => item.id === form.mode)
    if (!current || current.available) return
    const fallback = list.find((item) => item.available && item.id !== 'vc')
    if (fallback) form.mode = fallback.id
  },
  { immediate: true },
)

onMounted(() => {
  void history.syncRemote()
})

function validate(): boolean {
  if (!currentMode.value) {
    formError.value = '请选择合成模式'
    return false
  }
  if (!currentMode.value.available) {
    formError.value = `当前模型不支持「${currentMode.value.label}」：${currentMode.value.note}`
    return false
  }
  if (needs('text') && !form.ttsText.trim()) {
    formError.value = '请输入需要合成的文本'
    return false
  }
  if (form.ttsText.length > maxTextLength.value) {
    formError.value = `文本长度 ${form.ttsText.length} 超出上限 ${maxTextLength.value} 字`
    return false
  }
  if (needs('speaker') && !form.speakerValue && !form.voiceValue) {
    formError.value = '请选择预训练音色或自定义音色'
    return false
  }
  if (form.voiceValue) {
    const picked = voices.byId(form.voiceValue)
    if (picked && !picked.prompt_text) {
      formError.value = `音色「${picked.name}」缺少参考文本，无法注册进推理运行时，请先到「音色库」补充`
      return false
    }
  }
  if (needs('prompt_text') && !form.voiceValue && !form.promptText.trim()) {
    formError.value = '请输入参考文本（需与参考音频内容一致）'
    return false
  }
  if (needs('instruct_text') && !form.instructText.trim()) {
    formError.value = '请输入风格指令文本'
    return false
  }
  if (needs('prompt_audio') && !form.voiceValue && !promptAudio.value) {
    formError.value = '请上传或录制参考音频'
    return false
  }
  if (needs('source_audio') && !sourceAudio.value) {
    formError.value = '请上传需要转换的源音频'
    return false
  }
  formError.value = ''
  return true
}

watch(promptAudio, (audio) => {
  if (!audio) {
    voiceName.value = ''
    return
  }
  if (voiceName.value.trim()) return
  const base = audio.file.name.replace(/\.[^.]+$/, '')
  voiceName.value = /^recording$/i.test(base)
    ? `复刻音色 ${new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(/[/:]/g, '')}`
    : base
})

function buildPayload(): SynthesisPayload {
  return {
    mode: form.mode,
    ttsText: form.ttsText.trim(),
    spkId: form.speakerValue,
    voiceId: form.voiceValue,
    promptText: form.promptText.trim(),
    instructText: form.instructText.trim(),
    speed: form.speed,
    seed: form.seed,
    textFrontend: form.textFrontend,
    saveVoice: saveVoice.value && !form.voiceValue && Boolean(promptAudio.value),
    voiceName: voiceName.value.trim(),
    promptAudio: promptAudio.value?.file ?? null,
    promptFilename: promptAudio.value?.file.name,
    sourceAudio: sourceAudio.value?.file ?? null,
    sourceFilename: sourceAudio.value?.file.name,
  }
}

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return Math.random().toString(36).slice(2, 12)
}

function record(item: GenerationItem): void {
  lastResult.value = item
  history.add(item)
}

async function generate(): Promise<void> {
  if (generating.value) return
  if (!validate()) {
    toast.error(formError.value)
    return
  }

  if (lastBlobUrl) {
    URL.revokeObjectURL(lastBlobUrl)
    lastBlobUrl = ''
  }

  const payload = buildPayload()
  const startedAt = performance.now()

  try {
    busy.value = true
    if (useStream.value) {
      stream.reset()
      const { audioId, voiceId } = await stream.start(payload)
      const elapsed = (performance.now() - startedAt) / 1000
      const blob = stream.toWavBlob()
      const url = blob ? URL.createObjectURL(blob) : ''
      lastBlobUrl = url
      const duration = stream.receivedDuration.value
      record({
        id: audioId || newId(),
        mode: form.mode,
        modeLabel: currentMode.value?.label ?? form.mode,
        text: form.ttsText.trim(),
        voiceLabel: voiceLabel.value,
        duration,
        createdAt: new Date().toISOString(),
        localUrl: url || undefined,
        remoteUrl: audioId ? `/api/v1/tts/audio/${audioId}` : undefined,
        sampleRate: system.model?.sample_rate ?? undefined,
        rtf: duration > 0 ? Number((elapsed / duration).toFixed(2)) : undefined,
      })
      toast.success(`合成完成（流式，${formatDuration(duration)}）`)
      await handleSavedVoice(voiceId)
    } else {
      const result = await synthesize(payload)
      const elapsed = (performance.now() - startedAt) / 1000
      const url = URL.createObjectURL(result.blob)
      lastBlobUrl = url
      record({
        id: result.audioId || newId(),
        mode: form.mode,
        modeLabel: currentMode.value?.label ?? form.mode,
        text: form.ttsText.trim(),
        voiceLabel: voiceLabel.value,
        duration: result.duration,
        createdAt: new Date().toISOString(),
        localUrl: url,
        remoteUrl: result.remoteUrl || undefined,
        sampleRate: result.sampleRate,
        rtf: result.duration > 0 ? Number((elapsed / result.duration).toFixed(2)) : undefined,
      })
      toast.success(`合成完成（${formatDuration(result.duration)}）`)
      await handleSavedVoice(result.voiceId)
    }
    // 首次合成会顺带加载模型，这里刷新一次以同步内置音色与运行状态
    void system.refresh().catch(() => undefined)
  } catch (error) {
    const message = errorMessage(error)
    formError.value = message
    toast.error(message)
  } finally {
    busy.value = false
  }
}

async function handleSavedVoice(voiceId: string): Promise<void> {
  if (!voiceId) return
  promptAudio.value = null
  await voices.refresh()
  const saved = voices.byId(voiceId)
  toast.success(`音色「${saved?.name ?? voiceId}」已保存到音色库，下次可直接选用`)
}

function stopGenerate(): void {
  stream.stop()
  busy.value = false
}

function useSample(text: string): void {
  form.ttsText = text
}

function rollSeed(): void {
  form.seed = Math.floor(Math.random() * 100000000)
}

function removeResult(id: string): void {
  history.remove(id)
  if (lastResult.value?.id === id) lastResult.value = null
}

async function refreshVoices(): Promise<void> {
  await voices.refresh()
  toast.success('音色库已刷新')
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>语音合成</h1>
      <p>
        支持预训练音色、3s 极速复刻、跨语种复刻与自然语言控制。当前
        <strong>{{ system.model?.family || '模型未加载' }}</strong>
      </p>
    </div>
    <div class="inline">
      <button class="btn ghost" type="button" @click="refreshVoices">刷新音色</button>
    </div>
  </div>

  <div class="grid two">
    <section>
      <div class="card">
        <ModeTabs v-model="form.mode" :modes="system.modes" />

        <div v-if="system.model?.state === 'ready' && system.model.device === 'cpu'" class="alert info">
          <strong>当前为 CPU 推理，速度约为实时的 1/50 ~ 1/100。</strong>
          <div class="alert-detail">
            实测（i7-7700HQ / CosyVoice2-0.5B）：3 秒语音约需 5 分钟。
            建议：① 关闭下方「流式合成」（CPU 上非流式反而更快）；② 每次只合成一两句短文本；
            ③ 对性能有要求时改用 NVIDIA GPU 机器（本机 CPU 上 RTF ≈ 100）。
          </div>
        </div>

        <div v-if="system.model && system.model.state !== 'ready'" class="alert warning">
          <template v-if="system.model.state === 'loading'">模型正在加载中，请稍候…</template>
          <template v-else-if="system.model.state === 'error'">模型加载失败：{{ system.model.error }}</template>
          <template v-else>
            模型尚未加载：首次合成会自动触发加载（真实模型可能需要数分钟），也可以到「设置」页手动加载。
          </template>
        </div>

        <p v-if="currentMode" class="mode-desc">
          {{ currentMode.description }}
          <span v-if="currentMode.note" class="note">{{ currentMode.note }}</span>
        </p>

        <div v-if="formError" class="alert error">{{ formError }}</div>

        <template v-if="needs('text')">
          <div class="field">
            <label for="tts-text">合成文本</label>
            <textarea
              id="tts-text"
              v-model="form.ttsText"
              :maxlength="maxTextLength"
              placeholder="请输入需要合成的文本，支持中英日韩等多语种…"
            />
            <span class="sub">{{ form.ttsText.length }} / {{ maxTextLength }} 字</span>
          </div>
          <div class="inline samples">
            <span class="dim">示例：</span>
            <button
              v-for="(item, index) in samples"
              :key="index"
              class="chip"
              type="button"
              :title="item"
              @click="useSample(item)"
            >
              示例 {{ index + 1 }}
            </button>
          </div>
        </template>

        <div v-if="showVoicePicker" class="field">
          <label>{{ needs('speaker') ? '音色选择' : '音色库（可选）' }}</label>
          <VoicePicker
            v-model:speaker-value="form.speakerValue"
            v-model:voice-value="form.voiceValue"
            :speakers="needs('speaker') ? system.speakers : []"
            :voices="form.mode === 'sft' || supportsVoiceLibrary ? voices.items : []"
            :allow-presets="needs('speaker')"
          />
          <span v-if="supportsVoiceLibrary" class="sub">
            选择已保存音色可直接复用；未选择时请上传或录制参考音频。
          </span>
        </div>

        <template v-if="needs('prompt_text') && !form.voiceValue">
          <div class="field">
            <label for="prompt-text">参考文本</label>
            <textarea
              id="prompt-text"
              v-model="form.promptText"
              class="small"
              placeholder="请填写与参考音频完全一致的文本内容，用于提升复刻相似度…"
            />
            <span class="sub">需与参考音频逐字一致；参考音频越清晰，复刻效果越好。</span>
          </div>
        </template>

        <template v-if="needs('instruct_text')">
          <div class="field">
            <label for="instruct-text">风格指令</label>
            <input
              id="instruct-text"
              v-model="form.instructText"
              type="text"
              placeholder="例如：用四川话说这句话 / 用开心的语气朗读"
            />
            <span class="sub">
              CosyVoice 2.0 / 3.0 会自动补全 &lt;|endofprompt|&gt;；支持的指令包括方言、情感、语速、音量等。
            </span>
          </div>
        </template>

        <div v-if="needs('prompt_audio') && !form.voiceValue" class="field">
          <AudioInput
            v-model="promptAudio"
            :label="form.voiceValue ? '参考音频（已选择音色库音色，可不上传）' : '参考音频'"
            :hint="`建议 3~${system.limits.max_prompt_seconds} 秒清晰人声，自动转码为 16kHz 单声道 WAV`"
            :max-seconds="system.limits.max_prompt_seconds"
          />
        </div>

        <div v-if="needs('prompt_text') && promptAudio && !form.voiceValue" class="field save-voice">
          <label class="checkbox">
            <input v-model="saveVoice" type="checkbox" />
            同时保存到音色库（下次可直接选用，无需重新上传参考音频）
          </label>
          <input
            v-model="voiceName"
            class="name-input"
            type="text"
            :disabled="!saveVoice"
            placeholder="音色名称（留空自动生成）"
          />
        </div>

        <div v-if="needs('source_audio')" class="field">
          <AudioInput
            v-model="sourceAudio"
            label="源音频（将被转换的音色）"
            hint="上传需要做音色转换的原始音频"
            :max-seconds="system.limits.max_prompt_seconds"
          />
        </div>

        <details class="advanced">
          <summary>高级参数</summary>
          <div class="advanced-body">
            <div class="field">
              <label for="speed">
                语速 <span class="dim">{{ form.speed.toFixed(2) }}x</span>
              </label>
              <input
                id="speed"
                v-model.number="form.speed"
                type="range"
                :min="system.limits.speed.min"
                :max="system.limits.speed.max"
                step="0.05"
                :disabled="currentMode ? !currentMode.supports_speed : false"
              />
            </div>

            <div class="row">
              <div class="field">
                <label for="seed">随机种子（留空为随机）</label>
                <div class="inline">
                  <input id="seed" v-model.number="form.seed" type="number" placeholder="例如 42" />
                  <button class="btn ghost" type="button" @click="rollSeed">随机</button>
                  <button class="btn ghost" type="button" @click="form.seed = null">清空</button>
                </div>
              </div>
              <div class="field">
                <label>开关</label>
                <div class="switches">
                  <label class="checkbox">
                    <input v-model="form.textFrontend" type="checkbox" />
                    启用文本正则化（数字 / 符号自动规范化）
                  </label>
                  <label class="checkbox">
                    <input v-model="settings.state.streaming" type="checkbox" />
                    流式合成（边生成边播放）
                  </label>
                  <label class="checkbox">
                    <input v-model="settings.state.autoRegister" type="checkbox" />
                    自动注册音色库音色
                  </label>
                </div>
              </div>
            </div>
          </div>
        </details>

        <div class="actions">
          <button class="btn primary lg block" type="button" :disabled="generating" @click="generate">
            <span v-if="generating" class="spinner" />
            {{ generating ? '合成中…' : useStream ? '开始流式合成' : '开始合成' }}
          </button>
          <button v-if="stream.streaming.value" class="btn danger" type="button" @click="stopGenerate">停止</button>
        </div>
      </div>
    </section>

    <section>
      <div class="card">
        <div class="card-title">
          <h2>本次结果</h2>
          <span v-if="stream.streaming.value" class="tag success">
            流式接收中 {{ formatDuration(stream.receivedDuration.value) }}
          </span>
        </div>

        <div v-if="stream.error.value" class="alert error">{{ stream.error.value }}</div>

        <ResultCard v-if="lastResult" :item="lastResult" @remove="removeResult" />
        <div v-else class="empty">
          <span class="icon">🎧</span>
          合成结果会显示在这里，可直接播放与下载。
        </div>
      </div>

      <div class="card">
        <div class="card-title">
          <h2>最近生成</h2>
          <RouterLink class="hint" to="/history">查看全部 →</RouterLink>
        </div>

        <template v-if="history.items.length">
          <ResultCard
            v-for="item in history.items.slice(0, 4)"
            :key="item.id"
            :item="item"
            @remove="removeResult"
          />
        </template>
        <div v-else class="empty">暂无历史记录</div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.save-voice {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
}

.name-input {
  max-width: 320px;
}

.alert-detail {
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.6;
  word-break: break-word;
  opacity: 0.92;
}

.mode-desc {
  margin: 14px 0 18px;
  font-size: 13px;
  color: var(--text-muted);
}

.mode-desc .note {
  display: block;
  color: var(--warning);
  margin-top: 4px;
}

.samples {
  margin: -6px 0 16px;
}

.chip {
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-muted);
  font-size: 12px;
  font-family: inherit;
  padding: 3px 10px;
  border-radius: 999px;
  cursor: pointer;
}

.chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

textarea.small {
  min-height: 74px;
}

.advanced {
  margin: 6px 0 18px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
}

.advanced summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--text-muted);
  user-select: none;
}

.advanced-body {
  padding-top: 14px;
}

.switches {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
</style>
