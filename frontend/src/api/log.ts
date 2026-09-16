/**
 * 操作日志 API（前端规格 §44）。
 *
 * 对齐 `app/api/v1/logs.py`：
 *
 * | 函数               | 端点                                        |
 * | ------------------ | ------------------------------------------- |
 * | `listMyLogs`       | `GET   /logs`                               |
 * | `listResourceLogs` | `GET   /logs/{resource_type}/{resource_id}` |
 *
 * 两个端点都需要 `log:read` 权限；`GET /logs` 只返回**当前用户自己**的
 * 操作时间线（资源级隔离），`GET /logs/{type}/{id}` 由后端校验调用者对
 * 目标资源的归属（不在归属链 → 404）。
 *
 * 通用限制（页面须诚实降级，见 `docs/FRONTEND_API_MAPPING.md` §4-D16）：
 * 参数只有后端统一的 `skip` / `limit`（`limit` 上限 **100**），响应裸数组
 * **无 `total`**，也**没有**时间 / 操作类型等筛选参数——筛选只能做在客户端。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { OperationLog } from '@/types/log'

/** `GET /logs` —— 当前用户自己的操作日志，最新在前。 */
function listMyLogs(params?: PaginationParams): Promise<OperationLog[]> {
  return http.get<OperationLog[]>('/logs', { params })
}

/**
 * `GET /logs/{resource_type}/{resource_id}` —— 某个资源的操作日志。
 * 调用者必须对该资源有归属权限，否则 404（IDOR 防枚举）。
 */
function listResourceLogs(
  resourceType: string,
  resourceId: number,
  params?: PaginationParams,
): Promise<OperationLog[]> {
  return http.get<OperationLog[]>(`/logs/${resourceType}/${resourceId}`, { params })
}

export const logApi = { listMyLogs, listResourceLogs }
