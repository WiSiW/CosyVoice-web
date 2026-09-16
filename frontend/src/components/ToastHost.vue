<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<template>
  <div class="toast-host">
    <TransitionGroup name="toast">
      <div v-for="toast in toasts" :key="toast.id" class="toast" :class="toast.type">
        <span class="icon">{{ toast.type === 'success' ? '✅' : toast.type === 'error' ? '⚠️' : 'ℹ️' }}</span>
        <span class="message">{{ toast.message }}</span>
        <button class="close" type="button" aria-label="关闭" @click="dismiss(toast.id)">×</button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  right: 20px;
  bottom: 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  z-index: 200;
  max-width: min(380px, calc(100vw - 40px));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-elevated);
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow);
  font-size: 13px;
}

.toast.success {
  border-color: rgba(61, 220, 151, 0.5);
}

.toast.error {
  border-color: rgba(255, 107, 129, 0.55);
}

.toast .message {
  flex: 1;
  word-break: break-word;
}

.toast .close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  padding: 0 2px;
}

.toast-enter-active,
.toast-leave-active {
  transition: all 220ms ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
