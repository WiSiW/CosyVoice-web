import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const manifestPath = resolve(root, 'manifest.json')
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'))

const required = [
  manifest.background?.service_worker,
  manifest.action?.default_popup,
  manifest.options_page,
  'offscreen/offscreen.html',
].filter(Boolean)

for (const path of required) {
  const target = resolve(root, path)
  if (!existsSync(target)) {
    throw new Error(`manifest 引用的文件不存在: ${path}`)
  }
}

const offscreenSource = await readFile(resolve(root, 'offscreen/offscreen.js'), 'utf8')
if (offscreenSource.includes('chrome.storage')) {
  throw new Error('offscreen document 不能使用 chrome.storage，请通过 service worker 传值')
}

if (manifest.manifest_version !== 3) {
  throw new Error('必须使用 Manifest V3')
}
if (!manifest.permissions?.includes('tabCapture')) {
  throw new Error('缺少 tabCapture 权限')
}
if (!manifest.permissions?.includes('offscreen')) {
  throw new Error('缺少 offscreen 权限')
}

console.log(`Chrome extension OK: ${manifest.name} v${manifest.version}`)
