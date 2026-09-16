<script setup lang="ts">
import { computed } from 'vue'

import type { Voice } from '@/types'

const props = defineProps<{
  speakers: string[]
  voices: Voice[]
  speakerValue: string
  voiceValue: string
}>()

const emit = defineEmits<{
  'update:speakerValue': [value: string]
  'update:voiceValue': [value: string]
}>()

const selected = computed({
  get: () => (props.voiceValue ? `voice:${props.voiceValue}` : `spk:${props.speakerValue}`),
  set: (value: string) => {
    if (value.startsWith('voice:')) {
      emit('update:voiceValue', value.slice(6))
      emit('update:speakerValue', '')
    } else {
      emit('update:speakerValue', value.slice(4))
      emit('update:voiceValue', '')
    }
  },
})

const currentVoice = computed(() => props.voices.find((voice) => voice.id === props.voiceValue))
</script>

<template>
  <div class="picker">
    <select v-model="selected" class="select">
      <option value="spk:">请选择预训练音色</option>
      <optgroup v-if="speakers.length" label="模型预训练音色">
        <option v-for="speaker in speakers" :key="speaker" :value="`spk:${speaker}`">{{ speaker }}</option>
      </optgroup>
      <optgroup v-if="voices.length" label="自定义音色库">
        <option v-for="voice in voices" :key="voice.id" :value="`voice:${voice.id}`">
          {{ voice.name }}（{{ voice.language }} · {{ voice.audio.duration.toFixed(1) }}s）
        </option>
      </optgroup>
    </select>

    <p v-if="currentVoice" class="sub">
      <template v-if="currentVoice.prompt_text">
        参考文本：{{ currentVoice.prompt_text }}
      </template>
      <template v-else>
        <span class="warn">该音色缺少参考文本，仅可用于跨语种复刻模式。</span>
      </template>
    </p>
  </div>
</template>

<style scoped>
.select {
  width: 100%;
}

.sub {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-dim);
  word-break: break-word;
}

.warn {
  color: var(--warning);
}
</style>
