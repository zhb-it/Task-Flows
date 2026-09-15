/**
 * Axios 请求封装（前端规格 §37 / §40 / §41 / §10）。
 *
 * 调用链（规格 §37）：`View → api/ → utils/request.ts → Axios → FastAPI`。
 * 页面不直接写 `axios.get(...)`。
 *
 * 本模块承担四件事：
 *
 * 1. **解信封**：后端成功响应是 `{"data": ..., "message": "success"}`
 *    （`app/schemas/common.py`），这里统一剥掉外层，业务代码只拿到 `data`。
 * 2. **自动带令牌**：请求拦截器为业务端点补 `Authorization: Bearer <access>`。
 * 3. **401 自动刷新**：Access Token 失效时用 Refresh Token 换新对并重放原请求
 *    （规格 §10 的流程图）。并发 401 共享同一次刷新，避免刷新风暴。
 * 4. **统一错误**：把 Axios 的各种失败归一成 `ApiError`，并按 §41 给出中文提示。
 *
 * 关于刷新为什么在这里用裸 `axios` 而不是 `api/auth.ts`：
 * `api/auth.ts` → `utils/request.ts`，若请求层再反向 import 它就成了循环依赖。
 * 刷新是一个「必须绕开拦截器」的调用（否则 401 会被再次拦截后无限递归），
 * 用裸 axios 表达这个意图最直接。
 */

import axios, {
  AxiosError,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiEnvelope, ErrorDetail, ValidationErrorItem } from '@/types/common'
import type { TokenPair } from '@/types/auth'
import { tokenStorage } from '@/utils/storage'

const BASE_URL = import.meta.env.VITE_API_BASE_URL

/** 401 时不需要（也不能）走刷新流程的端点。 */
const AUTH_FREE_PATHS = ['/auth/login', '/auth/register', '/auth/refresh']

/** 归一化后的 API 错误。 */
export class ApiError extends Error {
  /** HTTP 状态码；网络层失败（无响应）时为 0。 */
  readonly status: number
  /** 后端原始 `detail`，便于调用方做精细判断。 */
  readonly detail: ErrorDetail | null

  constructor(message: string, status: number, detail: ErrorDetail | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** 在 `AxiosRequestConfig` 之上追加的项目自定义开关。 */
export interface RequestOptions extends AxiosRequestConfig {
  /** 静默模式：不弹统一错误提示，由调用方自己处理（轮询、探测类请求）。 */
  silent?: boolean
}

/** 带内部标记的请求配置（`_retried` 防止刷新后重放再次触发刷新）。 */
interface RetriableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
  silent?: boolean
}

/** §41 的状态码 → 中文提示。 */
const STATUS_MESSAGES: Record<number, string> = {
  400: '请求参数错误',
  401: '登录状态已失效，请重新登录',
  403: '没有权限执行该操作',
  404: '数据不存在',
  409: '数据冲突，请刷新后重试',
  422: '参数校验失败',
  429: '请求过于频繁，请稍后再试',
  500: '服务器异常，请稍后重试',
}

function isAuthFree(url?: string): boolean {
  return typeof url === 'string' && AUTH_FREE_PATHS.some((path) => url.includes(path))
}

/** 从 `detail` 里抽出可展示的文案。422 是数组，取第一条并以字段路径前缀。 */
function detailToText(detail: ErrorDetail | null): string | null {
  if (typeof detail === 'string' && detail.length > 0) {
    return detail
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item: ValidationErrorItem) => {
        const field = item.loc.filter((part) => part !== 'body').join('.')
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join('；')
  }
  return null
}

/** 把任意异常归一成 `ApiError`。 */
function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error
  }
  if (error instanceof AxiosError) {
    const status = error.response?.status ?? 0
    const detail = (error.response?.data as { detail?: ErrorDetail } | undefined)?.detail ?? null
    const fallback =
      status === 0 ? '网络异常，请检查网络连接后重试' : (STATUS_MESSAGES[status] ?? '请求失败，请稍后重试')
    return new ApiError(detailToText(detail) ?? fallback, status, detail)
  }
  return new ApiError('请求失败，请稍后重试', 0, null)
}

/**
 * 生成给用户看的提示。
 *
 * 登录/注册这类未认证端点复用 §41 的通用文案会答非所问（「登录状态已失效」出现
 * 在登录失败时很奇怪），所以对它们使用后端语义对应的文案。
 */
function userMessage(error: ApiError, config?: RetriableConfig): string {
  if (error.status === 0) {
    return '网络异常，请检查网络连接后重试'
  }
  if (isAuthFree(config?.url)) {
    if (error.status === 401) return '用户名或密码错误'
    if (error.status === 403) return '账号已被禁用，请联系管理员'
    if (error.status === 409) return detailToText(error.detail) ?? '用户名或邮箱已被注册'
  }
  return STATUS_MESSAGES[error.status] ?? detailToText(error.detail) ?? '请求失败，请稍后重试'
}

const instance = axios.create({
  baseURL: BASE_URL,
  // 后端有 60s/60 请求的滑动窗口限流（`app/core/middleware.py`），超时设太短会
  // 把正常竞态误报成失败，太长又让用户干等；15s 是常见折中。
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

instance.interceptors.request.use((config) => {
  const token = tokenStorage.getAccessToken()
  if (token && !isAuthFree(config.url)) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

/**
 * 刷新中的 Promise（单飞 / single-flight）。
 *
 * 并发场景很常见：进入页面时同时发起多个请求，Access Token 恰好过期，会同时收到
 * 多个 401。如果各自去刷新，后到的刷新会拿着**已被轮换撤销**的 Refresh Token 请求，
 * 后端一律拒绝（`rotate_tokens` 对已撤销 jti 返回 401），结果是「刷新把用户踢下线」。
 * 共享同一个 Promise 后，只刷新一次，其余请求等同一个结果。
 */
let refreshing: Promise<string> | null = null

/** 刷新失败（Refresh Token 也不可用）时的回调，由路由层注册。 */
type UnauthorizedHandler = () => void
let unauthorizedHandler: UnauthorizedHandler | null = null

/**
 * 注册「会话彻底失效」的处理逻辑（清凭证 + 跳登录）。
 *
 * 用回调注册而不是在请求层 import router：`router/guards.ts` 会 import 本模块，
 * 本模块若 import router 就构成循环依赖。
 */
export function onUnauthorized(handler: UnauthorizedHandler): void {
  unauthorizedHandler = handler
}

async function requestNewAccessToken(): Promise<string> {
  const refreshToken = tokenStorage.getRefreshToken()
  if (!refreshToken) {
    throw new ApiError('登录状态已失效，请重新登录', 401, null)
  }
  try {
    const response = await axios.post<ApiEnvelope<TokenPair>>(
      `${BASE_URL}/auth/refresh`,
      { refresh_token: refreshToken },
      { timeout: 15_000, headers: { Accept: 'application/json' } },
    )
    tokenStorage.save(response.data.data)
    return response.data.data.access_token
  } catch (error) {
    throw toApiError(error)
  }
}

instance.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined

    const shouldRefresh =
      error.response?.status === 401 && config != null && config._retried !== true && !isAuthFree(config.url)

    if (shouldRefresh && config) {
      config._retried = true
      try {
        refreshing ??= requestNewAccessToken().finally(() => {
          refreshing = null
        })
        const accessToken = await refreshing
        config.headers.set('Authorization', `Bearer ${accessToken}`)
        return await instance.request(config)
      } catch (refreshError) {
        // Refresh Token 也失效：清空本地凭证并交给路由层跳登录（规格 §10 末段）。
        const apiError = toApiError(refreshError)
        tokenStorage.clear()
        unauthorizedHandler?.()
        return Promise.reject(apiError)
      }
    }

    const apiError = toApiError(error)
    if (config?.silent !== true && apiError.status !== 401) {
      ElMessage.error(userMessage(apiError, config))
    }
    return Promise.reject(apiError)
  },
)

/** 解信封：`AxiosResponse<ApiEnvelope<T>>` → `T`。 */
async function unwrap<T>(promise: Promise<AxiosResponse<ApiEnvelope<T>>>): Promise<T> {
  const response = await promise
  return response.data.data
}

/**
 * 业务 API 使用的请求对象。
 *
 * `http.get<Task[]>('/tasks')` 直接得到 `Task[]`——信封、令牌、刷新、报错都已处理。
 */
export const http = {
  get<T>(url: string, options?: RequestOptions): Promise<T> {
    return unwrap<T>(instance.get<ApiEnvelope<T>>(url, options))
  },
  post<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return unwrap<T>(instance.post<ApiEnvelope<T>>(url, body, options))
  },
  patch<T>(url: string, body?: unknown, options?: RequestOptions): Promise<T> {
    return unwrap<T>(instance.patch<ApiEnvelope<T>>(url, body, options))
  },
  delete<T>(url: string, options?: RequestOptions): Promise<T> {
    return unwrap<T>(instance.delete<ApiEnvelope<T>>(url, options))
  },
}
