import axios, { AxiosError, type AxiosRequestConfig } from 'axios'

import type { ApiError } from '@/types'

import { apiUrl } from './runtime'

/** 统一的请求异常，消息可直接展示给用户。 */
export class RequestError extends Error {
  readonly code: string
  readonly status?: number

  constructor(message: string, code = 'request_error', status?: number) {
    super(message)
    this.name = 'RequestError'
    this.code = code
    this.status = status
  }
}

export const http = axios.create({
  timeout: 120_000,
  headers: { Accept: 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ error?: ApiError }>) => {
    const payload = error.response?.data?.error
    if (payload?.message) {
      return Promise.reject(new RequestError(payload.message, payload.code, error.response?.status))
    }
    if (error.code === 'ERR_NETWORK') {
      return Promise.reject(
        new RequestError('无法连接后端服务，请确认后端已启动，或在「设置」中检查 API 地址', 'network_error'),
      )
    }
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new RequestError('请求超时，请稍后重试或缩短文本长度', 'timeout'))
    }
    return Promise.reject(new RequestError(error.message || '请求失败', error.code, error.response?.status))
  },
)

export async function get<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.get<T>(apiUrl(path), config)
  return data
}

export async function post<T>(path: string, body?: unknown, config?: AxiosRequestConfig): Promise<T> {
  const { data } = await http.post<T>(apiUrl(path), body, config)
  return data
}

export async function patch<T>(path: string, body?: unknown): Promise<T> {
  const { data } = await http.patch<T>(apiUrl(path), body)
  return data
}

export async function del(path: string): Promise<void> {
  await http.delete(apiUrl(path))
}

/** 从任意异常中提取可展示的消息 */
export function errorMessage(error: unknown): string {
  if (error instanceof RequestError) return error.message
  if (error instanceof Error) return error.message
  return String(error)
}
