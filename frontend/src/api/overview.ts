/**
 * 个人工作台聚合 API（TASK-129，规格 §61.6「个人视图」）。
 *
 * 对齐 `app/api/v1/users.py::read_my_overview`：
 *
 * | 函数           | 端点                        |
 * | -------------- | --------------------------- |
 * | `getMyOverview`| `GET /users/me/overview`    |
 *
 * 只要求认证，不要求功能级权限（查的是自己的工作台）。
 *
 * 为什么单独一个端点而不是让首页连打五六个接口：Bento 首页一屏要六个数字，
 * 逐个拉既慢又容易半屏半屏地闪；后端一次聚合返回，前端只有一次加载态。
 */

import { http, type RequestOptions } from '@/utils/request'
import type { MeOverview } from '@/types/overview'

/** `GET /users/me/overview` 的查询参数。 */
export interface OverviewParams {
  /** 「最近项目」返回条数，后端约束 1~20，默认 5。 */
  recent_limit?: number
}

/** `GET /users/me/overview` —— 当前用户的工作台聚合。 */
function getMyOverview(
  params?: OverviewParams,
  options?: RequestOptions,
): Promise<MeOverview> {
  return http.get<MeOverview>('/users/me/overview', { ...options, params })
}

export const overviewApi = {
  getMyOverview,
}
