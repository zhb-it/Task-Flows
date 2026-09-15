/**
 * 通知类型（前端规格 §39）。
 *
 * 对齐 `app/schemas/notification.py`：
 * - `NotificationRead{id, user_id, type, title, content, is_read, created_at}`
 * - `NotificationMarkAllRead{marked}`
 *
 * ⚠ 后端**没有**「未读数」端点：`GET /api/v1/notifications` 只返回列表，
 * 因此顶部铃铛的未读数只能由前端在已取回的列表上自行统计
 * （见 `src/stores/notification.ts`）。列表默认 `limit=100` 且有上限 `le=100`，
 * 所以未读数在通知数量超过 100 条时会偏小——这是后端的既有限制，不是前端 bug。
 */

/** `GET /api/v1/notifications` 列表项。 */
export interface Notification {
  id: number
  user_id: number
  /** 业务类型字符串（由后端派发时决定）。 */
  type: string
  title: string
  content: string | null
  is_read: boolean
  created_at: string
}

/** `PATCH /api/v1/notifications/read-all` 的 `data`。 */
export interface NotificationMarkAllRead {
  /** 本次真正从未读翻转为已读的条数（幂等：重复调用返回 0）。 */
  marked: number
}
