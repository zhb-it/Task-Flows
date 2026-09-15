/**
 * `utils/request.ts` 的单元测试。
 *
 * 怎么在不造假后端的前提下测请求层：给每个请求传一个**自定义 adapter**
 * （`RequestOptions` 继承自 `AxiosRequestConfig`，所以 `adapter` 是公开可传的）。
 * 这样测的是真实代码路径——拦截器、信封解包、错误归一都真的跑了一遍，
 * 只有「网络」这一层被替换掉。
 *
 * 401 自动刷新那一段没有放在这里：它的刷新调用走的是裸 `axios`（故意绕开拦截器），
 * 无法用同样的方式注入 adapter。那条路径由真实联调覆盖（前端阶段 3 的验收项）。
 */

import { AxiosError, AxiosHeaders, type AxiosAdapter, type AxiosResponse } from 'axios'
import { beforeEach, describe, expect, it } from 'vitest'

import { ApiError, http } from '@/utils/request'
import { tokenStorage } from '@/utils/storage'

/** 构造一个始终返回给定 JSON 体的 adapter。 */
function adapterReturning(body: unknown, status = 200): AxiosAdapter {
  return async (config) =>
    ({
      data: body,
      status,
      statusText: 'OK',
      headers: new AxiosHeaders(),
      config,
    }) as AxiosResponse
}

/** 构造一个始终以给定状态码失败的 adapter（模拟后端的错误信封）。 */
function adapterFailing(status: number, body: unknown): AxiosAdapter {
  return async (config) => {
    const response = {
      data: body,
      status,
      statusText: 'ERROR',
      headers: new AxiosHeaders(),
      config,
    } as AxiosResponse
    throw new AxiosError(
      `Request failed with status code ${status}`,
      String(status),
      config,
      undefined,
      response,
    )
  }
}

async function expectApiError(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError)
    return error as ApiError
  }
  throw new Error('期望请求被拒绝，但它成功返回了')
}

describe('http 解信封', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('GET 直接返回信封里的 data', async () => {
    const adapter = adapterReturning({
      data: { id: 7, username: 'alice' },
      message: 'success',
    })

    const user = await http.get<{ id: number; username: string }>('/users/me', { adapter })

    expect(user).toEqual({ id: 7, username: 'alice' })
  })

  it('列表端点返回数组（后端的 list 直接放在 data 里）', async () => {
    const adapter = adapterReturning({ data: [{ id: 1 }, { id: 2 }], message: 'success' })

    const items = await http.get<Array<{ id: number }>>('/teams', { adapter })

    expect(items).toHaveLength(2)
  })

  it('POST 把请求体原样发出（字段名与后端契约一致）', async () => {
    let received: unknown
    const adapter: AxiosAdapter = async (config) => {
      received = JSON.parse(String(config.data))
      return {
        data: { data: { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }, message: 'success' },
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
      } as AxiosResponse
    }

    await http.post('/auth/login', { username: 'alice', password: 'secret' }, { adapter })

    expect(received).toEqual({ username: 'alice', password: 'secret' })
  })
})

describe('http 自动携带令牌', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('有 Access Token 时补上 Authorization', async () => {
    tokenStorage.save({ access_token: 'access-1', refresh_token: 'refresh-1', token_type: 'bearer' })

    let authorization: unknown
    const adapter: AxiosAdapter = async (config) => {
      authorization = config.headers.get('Authorization')
      return {
        data: { data: null, message: 'success' },
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
      } as AxiosResponse
    }

    await http.get('/teams', { adapter })

    expect(authorization).toBe('Bearer access-1')
  })

  it('登录端点不带 Authorization（避免用旧令牌覆盖登录语义）', async () => {
    tokenStorage.save({ access_token: 'stale', refresh_token: 'refresh-1', token_type: 'bearer' })

    let authorization: unknown = 'unset'
    const adapter: AxiosAdapter = async (config) => {
      authorization = config.headers.get('Authorization')
      return {
        data: { data: { access_token: 'a', refresh_token: 'r', token_type: 'bearer' }, message: 'success' },
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
      } as AxiosResponse
    }

    await http.post('/auth/login', { username: 'a', password: 'b' }, { adapter })

    expect(authorization).toBeUndefined()
  })

  it('没有令牌时不写 Authorization 头', async () => {
    let authorization: unknown = 'unset'
    const adapter: AxiosAdapter = async (config) => {
      authorization = config.headers.get('Authorization')
      return {
        data: { data: null, message: 'success' },
        status: 200,
        statusText: 'OK',
        headers: new AxiosHeaders(),
        config,
      } as AxiosResponse
    }

    await http.get('/teams', { adapter })

    expect(authorization).toBeUndefined()
  })
})

describe('http 错误归一', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('后端的字符串 detail 会被保留为错误信息', async () => {
    const adapter = adapterFailing(404, { detail: 'Task not found' })

    const error = await expectApiError(http.get('/tasks/999', { adapter, silent: true }))

    expect(error.status).toBe(404)
    expect(error.message).toBe('Task not found')
  })

  it('422 的数组 detail 会被拼成可读文案（带字段路径）', async () => {
    const adapter = adapterFailing(422, {
      detail: [
        { loc: ['body', 'title'], msg: 'Field required', type: 'missing' },
        { loc: ['body', 'priority'], msg: 'Input should be a valid enum', type: 'enum' },
      ],
    })

    const error = await expectApiError(http.post('/tasks', {}, { adapter, silent: true }))

    expect(error.status).toBe(422)
    expect(error.message).toContain('title: Field required')
    expect(error.message).toContain('priority: Input should be a valid enum')
  })

  it('没有 detail 时回落到状态码对应的通用文案', async () => {
    const adapter = adapterFailing(500, {})

    const error = await expectApiError(http.get('/teams', { adapter, silent: true }))

    expect(error.status).toBe(500)
    expect(error.message).toBe('服务器异常，请稍后重试')
  })

  it('被封装的 detail 是结构化数据（调用方可以进一步判断）', async () => {
    const adapter = adapterFailing(403, { detail: 'Permission denied: task:delete' })

    const error = await expectApiError(http.delete('/tasks/1', { adapter, silent: true }))

    expect(error.detail).toBe('Permission denied: task:delete')
  })
})
