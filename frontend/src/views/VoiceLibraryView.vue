<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'

import { errorMessage } from '@/api/client'
import { fetchVoicePresets, voiceAudioUrl } from '@/api/voices'
import AudioInput from '@/components/AudioInput.vue'
import AudioPlayer from '@/components/AudioPlayer.vue'
import { useToast } from '@/composables/useToast'
import { useSettingsStore } from '@/stores/settings'
import { useSystemStore } from '@/stores/system'
import { useVoiceStore } from '@/stores/voices'
import type { PreparedAudio, Voice, VoicePreset } from '@/types'
import { formatBytes, formatDateTime, formatDuration } from '@/utils/format'

const voices = useVoiceStore()
const system = useSystemStore()
const settings = useSettingsStore()
const toast = useToast()

const showCreate = ref(false)
const presets = ref<VoicePreset[]>([])
const fallbackNote = ref('')
const submitting = ref(false)
const editingId = ref('')
const busyId = ref('')

const draft = reactive({
  name: '',
  description: '',
  language: '中文',
  promptText: '',
  audio: null as PreparedAudio | null,
})

const editDraft = reactive({ name: '', description: '', promptText: '', language: '中文' })

const presetByLanguage = computed(() => {
  const map = new Map<string, VoicePreset>()
  for (const preset of presets.value) map.set(preset.language, preset)
  return map
})

const currentPreset = computed(() => presetByLanguage.value.get(draft.language) ?? null)

/** 一键填入当前语种的朗读稿 */
function applyPreset(force = true): void {
  const preset = currentPreset.value
  if (!preset) return
  if (force || !draft.promptText.trim()) draft.promptText = preset.text
}

async function loadPresets(): Promise<void> {
  try {
    const data = await fetchVoicePresets()
    presets.value = data.presets
    fallbackNote.value = data.fallback_note
    // 首次进入时按当前语种预置参考文本
    if (!draft.promptText.trim()) applyPreset()
  } catch {
    /* 预置稿属于辅助信息，取不到不影响手动填写 */
  }
}

/**
 * 切换语种时同步预置稿。
 * 只有在「文本为空」或「仍是上一个语种的预置稿」时才覆盖，避免冲掉用户已填内容。
 */
watch(
  () => draft.language,
  (language, previous) => {
    const next = presetByLanguage.value.get(language)
    if (!next) return
    const current = draft.promptText.trim()
    const previousPreset = previous ? presetByLanguage.value.get(previous)?.text.trim() : undefined
    if (!current || current === previousPreset) {
      draft.promptText = next.text
    }
  },
)

onMounted(() => {
  void loadPresets()
})

function resetDraft(): void {
  draft.name = ''
  draft.description = ''
  draft.language = voices.languages[0] ?? '中文'
  draft.promptText = ''
  draft.audio = null
  applyPreset()
}

async function submit(): Promise<void> {
  if (!draft.name.trim()) {
    toast.error('请填写音色名称')
    return
  }
  if (!draft.audio) {
    toast.error('请上传或录制参考音频')
    return
  }
  if (!draft.promptText.trim()) {
    toast.error('请填写参考文本：缺少参考文本的音色无法注册进推理运行时，也就无法用于合成')
    return
  }

  submitting.value = true
  try {
    const voice = await voices.create({
      name: draft.name.trim(),
      audio: draft.audio.file,
      filename: draft.audio.file.name,
      promptText: draft.promptText.trim(),
      description: draft.description.trim(),
      language: draft.language,
      source: draft.audio.source,
      autoRegister: settings.state.autoRegister,
    })
    toast.success(`音色「${voice.name}」已创建`)
    void system.refresh().catch(() => undefined)
    resetDraft()
    showCreate.value = false
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}

function startEdit(voice: Voice): void {
  editingId.value = voice.id
  editDraft.name = voice.name
  editDraft.description = voice.description
  editDraft.promptText = voice.prompt_text
  editDraft.language = voice.language
}

async function saveEdit(id: string): Promise<void> {
  busyId.value = id
  try {
    await voices.update(id, {
      name: editDraft.name,
      description: editDraft.description,
      prompt_text: editDraft.promptText,
      language: editDraft.language,
    })
    if (settings.state.autoRegister && editDraft.promptText.trim() && system.ready) {
      await voices.register(id)
    }
    void system.refresh().catch(() => undefined)
    editingId.value = ''
    toast.success('已保存')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busyId.value = ''
  }
}

async function register(id: string): Promise<void> {
  busyId.value = id
  try {
    const voice = await voices.register(id)
    if (voice.registered) toast.success('音色已加载到推理运行时')
    else toast.info('音色已注册，模型就绪后会生效')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busyId.value = ''
  }
}

async function remove(voice: Voice): Promise<void> {
  if (!window.confirm(`确定删除音色「${voice.name}」吗？该操作不可撤销。`)) return
  busyId.value = voice.id
  try {
    await voices.remove(voice.id)
    void system.refresh().catch(() => undefined)
    toast.success('音色已删除')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busyId.value = ''
  }
}
</script>

<template>
  <div class="page-header">
    <div>
      <h1>音色库</h1>
      <p>
        上传或录制 3~30 秒参考音频 + 填写对应参考文本即可创建专属音色，
        创建后可在合成页直接选用。<strong>参考文本为必填项</strong>：缺少它音色无法注册进推理运行时，也就无法用于合成。
      </p>
    </div>
    <button class="btn primary" type="button" @click="showCreate = !showCreate">
      {{ showCreate ? '收起' : '+ 新建音色' }}
    </button>
  </div>

  <div v-if="showCreate" class="card">
    <div class="card-title">
      <h2>新建音色</h2>
      <span class="hint">
        参考文本为必填项；文本越准确、音频越干净，合成相似度越高
      </span>
    </div>

    <div class="grid two">
      <div>
        <div class="field">
          <label for="voice-name">音色名称 *</label>
          <input id="voice-name" v-model="draft.name" type="text" placeholder="例如：沉稳男声 / 甜美客服" />
        </div>

        <div class="field">
          <label for="voice-lang">语言</label>
          <select id="voice-lang" v-model="draft.language">
            <option v-for="language in voices.languages" :key="language" :value="language">{{ language }}</option>
          </select>
        </div>

        <div class="field">
          <div class="label-row">
            <label for="voice-prompt">参考文本 *</label>
            <button
              v-if="currentPreset"
              class="chip"
              type="button"
              :title="`填入${draft.language}预置朗读稿`"
              @click="applyPreset(true)"
            >
              ↻ 填入{{ draft.language }}预置稿
            </button>
          </div>
          <textarea
            id="voice-prompt"
            v-model="draft.promptText"
            class="small"
            placeholder="请填写与参考音频完全一致的内容，例如：希望你以后能够做的比我还好呦。"
          />
          <span class="sub">
            需与参考音频逐字一致。缺少参考文本的音色无法注册，也就无法在合成页使用（必填）。
          </span>

          <div v-if="currentPreset" class="preset-tip">
            <p>
              <strong>推荐：照着上面这段朗读录制</strong>（约 {{ currentPreset.target_seconds }} 秒），
              文本与音频天然逐字一致。<template v-if="draft.audio?.source === 'upload'">
                若你上传的是已有录音，请改为填写该录音的真实内容，不要直接套用预置稿。</template>
            </p>
            <p class="dim">
              声纹（说话人向量）只由音频计算，文本不参与；但文本必须与音频对应，
              否则模型的音‑文对齐会错乱，复刻相似度会明显下降。
            </p>
          </div>
          <p v-else-if="fallbackNote" class="sub">{{ fallbackNote }}</p>
        </div>

        <div class="field">
          <label for="voice-desc">备注</label>
          <input id="voice-desc" v-model="draft.description" type="text" placeholder="可选，例如：适合播报 / 客服场景" />
        </div>
      </div>

      <div>
        <AudioInput
          v-model="draft.audio"
          label="参考音频 *"
          :hint="`支持上传或录制，${system.limits.max_prompt_seconds} 秒以内，自动转码为 16kHz 单声道 WAV`"
          :max-seconds="system.limits.max_prompt_seconds"
        />

        <div class="create-actions">
          <button class="btn primary" type="button" :disabled="submitting" @click="submit">
            <span v-if="submitting" class="spinner" />
            {{ submitting ? '创建中…' : '保存音色' }}
          </button>
          <button class="btn ghost" type="button" @click="resetDraft">重置</button>
        </div>
      </div>
    </div>
  </div>

  <div class="card">
    <div class="card-title">
      <h2>自定义音色（{{ voices.items.length }}）</h2>
      <button class="btn ghost" type="button" :disabled="voices.loading" @click="voices.refresh()">刷新</button>
    </div>

    <div v-if="voices.error" class="alert error">{{ voices.error }}</div>

    <div v-if="!voices.items.length" class="empty">
      <span class="icon">🎧</span>
      还没有自定义音色，点击右上角「新建音色」上传一段参考音频吧。
    </div>

    <div v-else class="voice-list">
      <article v-for="voice in voices.items" :key="voice.id" class="voice">
        <div class="top">
          <div class="title-row">
            <h3>{{ voice.name }}</h3>
            <span class="tag muted">{{ voice.language }}</span>
            <span class="tag" :class="voice.registered ? 'success' : 'muted'">
              {{ voice.registered ? '已加载' : '未加载' }}
            </span>
            <span class="tag muted">{{ voice.source === 'record' ? '录制' : '上传' }}</span>
          </div>
          <div class="ops">
            <button
              v-if="!voice.registered"
              class="btn ghost sm"
              type="button"
              :disabled="busyId === voice.id || !voice.prompt_text"
              :title="voice.prompt_text ? '注册到推理运行时' : '缺少参考文本，无法注册'"
              @click="register(voice.id)"
            >
              加载
            </button>
            <button class="btn ghost sm" type="button" @click="editingId === voice.id ? (editingId = '') : startEdit(voice)">
              {{ editingId === voice.id ? '取消' : '编辑' }}
            </button>
            <button class="btn danger sm" type="button" :disabled="busyId === voice.id" @click="remove(voice)">删除</button>
          </div>
        </div>

        <p v-if="voice.description" class="desc">{{ voice.description }}</p>

        <div class="facts">
          <span class="dim">时长 {{ formatDuration(voice.audio.duration) }}</span>
          <span class="dim">· {{ voice.audio.sample_rate }} Hz</span>
          <span class="dim">· {{ formatBytes(voice.audio.size) }}</span>
          <span class="dim">· 创建于 {{ formatDateTime(voice.created_at) }}</span>
        </div>

        <AudioPlayer
          v-if="editingId !== voice.id"
          :src="voiceAudioUrl(voice.id)"
          :title="`参考音频：${voice.audio.original_filename || voice.audio.filename}`"
          :download-name="`${voice.name}.wav`"
        />

        <div v-else class="edit">
          <div class="row">
            <div class="field">
              <label>名称</label>
              <input v-model="editDraft.name" type="text" />
            </div>
            <div class="field">
              <label>语言</label>
              <select v-model="editDraft.language">
                <option v-for="language in voices.languages" :key="language" :value="language">{{ language }}</option>
              </select>
            </div>
          </div>
          <div class="field">
            <label>参考文本 *</label>
            <textarea v-model="editDraft.promptText" class="small" />
            <span class="sub">缺少参考文本的音色无法注册，无法在合成页使用。</span>
          </div>
          <div class="field">
            <label>备注</label>
            <input v-model="editDraft.description" type="text" />
          </div>
          <button class="btn primary" type="button" :disabled="busyId === voice.id" @click="saveEdit(voice.id)">
            保存修改
          </button>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 7px;
}

.label-row label {
  margin-bottom: 0;
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

.preset-tip {
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--accent-soft);
  font-size: 12.5px;
  line-height: 1.7;
}

.preset-tip p {
  margin: 0;
}

.preset-tip p + p {
  margin-top: 4px;
}

textarea.small {
  min-height: 70px;
}

.create-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

.voice-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.voice {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px;
  background: var(--bg-elevated);
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.title-row h3 {
  font-size: 15px;
}

.ops {
  display: flex;
  gap: 4px;
}

.desc {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--text-muted);
}

.facts {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin: 8px 0 10px;
}

.edit {
  margin-top: 12px;
}

.edit .field {
  margin-bottom: 12px;
}

.btn.sm {
  padding: 5px 10px;
  font-size: 12px;
}
</style>
