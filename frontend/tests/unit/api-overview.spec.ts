/**
 * `api/overview.ts` 的单元测试（TASK-129）。
 *
 * 测什么：**端点路径与参数必须和后端一一对应**。前端规格 §57 明令「禁止猜
 * API / 编造接口」，而「猜错路径」是最容易悄悄发生的一种编造——页面会拿到
 * 404，却可能被误判成「后端还没实现」。这里用自定义 adapter 钉死请求行，
 * 后端一旦改名，这条测试先红。
 *
 * 不测什么：不测真实的聚合数字（那是后端 `tests/test_me_overview.py` 的
 * 职责），也不造假响应体去驱动页面——响应体用后端真实契约的最小实例。
 */

import { AxiosHeaders, type AxiosAdapter, type AxiosResponse } from 'axios'
import { describe, expect, it } from 'vitest'

import { overviewApi } from '@/api/overview'
import type { MeOverview } from '@/types/overview'

/** 捕获请求配置并返回给定信封体的 adapter。 */
function adapterCapturing(
  body: unknown,
  capture: { url?: string; params?: unknown }[],
): AxiosAdapter {
  return async (config) => {
    capture.push({ url: config.url, params: config.params })
    return {
      data: body,
      status: 200,
      statusText: 'OK',
      headers: new AxiosHeaders(),
      config,
    } as AxiosResponse
  }
}

/** 后端真实契约的最小实例（字段与 `MeOverviewRead` 同名）。 */
const overviewFixture: MeOverview = {
  generated_at: '2026-09-17T12:00:00+00:00',
  week_start: '2026-09-14T00:00:00+00:00',
  teams: 1,
  projects: 2,
  unread_notifications: 3,
  my_tasks: { assigned_open: 4, overdue: 1, completed_this_week: 2 },
  task_status: {
    TODO: 5,
    IN_PROGRESS: 3,
    REVIEW: 1,
    DONE: 7,
    CANCELLED: 0,
    total: 16,
  },
  recent_projects: [{ id: 11, name: 'Alpha', team_id: 1, updated_at: '2026-09-17T10:00:00+00:00' }],
}

describe('overviewApi.getMyOverview', () => {
  it('请求 GET /users/me/overview（经实例基址即 /api/v1/users/me/overview）', async () => {
    const capture: { url?: string; params?: unknown }[] = []

    const data = await overviewApi.getMyOverview(undefined, {
      adapter: adapterCapturing({ data: overviewFixture, message: 'success' }, capture),
    })

    expect(capture).toHaveLength(1)
    expect(capture[0]?.url).toBe('/users/me/overview')
    expect(data).toEqual(overviewFixture)
  })

  it('透传 recent_limit 查询参数', async () => {
    const capture: { url?: string; params?: unknown }[] = []

    await overviewApi.getMyOverview(
      { recent_limit: 5 },
      { adapter: adapterCapturing({ data: overviewFixture, message: 'success' }, capture) },
    )

    expect(capture[0]?.params).toEqual({ recent_limit: 5 })
  })

  it('不解包失败响应以外的字段：信封里的 message 不进入返回值', async () => {
    const data = await overviewApi.getMyOverview(undefined, {
      adapter: adapterCapturing({ data: overviewFixture, message: 'success' }, []),
    })

    expect(data).not.toHaveProperty('message')
    expect(data.my_tasks.overdue).toBe(1)
  })
})
