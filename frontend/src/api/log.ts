/**
 * 操作日志 API（前端规格 §44）。
 *
 * 对齐 `app/api/v1/logs.py`：
 *
 * | 函数           | 端点          |
 * | -------------- | ------------- |
 * | `listMyLogs`   | `GET   /logs` |
 *
 * `GET /logs` 需要 `log:read` 权限，只返回**当前用户自己**的操作时间线
 * （资源级日志 `GET /logs/{type}/{id}` 是另一端点）。列表参数是后端统一的
 * `skip` / `limit`，响应裸数组无 `total`。本阶段只取概览，传 `limit=5`。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { OperationLog } from '@/types/log'

/** `GET /logs` —— 当前用户自己的操作日志，最新在前。 */
function listMyLogs(params?: PaginationParams): Promise<OperationLog[]> {
  return http.get<OperationLog[]>('/logs', { params })
}

export const logApi = { listMyLogs }
