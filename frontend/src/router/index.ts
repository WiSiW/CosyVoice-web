import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'synthesis',
    component: () => import('@/views/SynthesisView.vue'),
    meta: { title: '语音合成', icon: '🎙️' },
  },
  {
    path: '/voices',
    name: 'voices',
    component: () => import('@/views/VoiceLibraryView.vue'),
    meta: { title: '音色库', icon: '🎧' },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/HistoryView.vue'),
    meta: { title: '生成记录', icon: '🗂️' },
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('@/views/SettingsView.vue'),
    meta: { title: '设置', icon: '⚙️' },
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const title = (to.meta.title as string | undefined) ?? ''
  document.title = title ? `${title} · CosyVoice 控制台` : 'CosyVoice 控制台'
})

export default router
