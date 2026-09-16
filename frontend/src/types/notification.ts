/**
 * 通知类型（前端规格 §30 / §31 / §39）。
 *
 * 对齐 `app/schemas/notification.py`：
 * - `NotificationRead{id, user_id, type, title, content, is_read, created_at}`
 * - `NotificationMarkAllRead{marked}`
 *
 * ⚠ 后端**没有**「未读数」端点：`GET /api/v1/notifications` 只返回列表，
 * 因此顶部铃铛的未读数只能由前端在已取回的列表上自行统计
 * （见 `src/stores/notification.ts`）。列表默认 `limit=100` 且有上限 `le=100`，
 * 所以未读数在通知数量超过 100 条时会偏小——这是后端的既有限制，不是前端 bug。
 *
 * ⚠ 后端**没有** link / resource_id 字段：规格 §30 要求「点击通知跳转对应资源」，
 * 但 `NotificationRead` 只有 `type` + `title` + `content`，资源编号仅作为文本出现在
 * `content` 里（如 `任务 #123 …`）。前端不解析正文字符串猜资源 id（会与后端文案强耦合，
 * 且 `team_invited` 等类型没有 id 可解析），因此通知列表不提供跳转，见 DECISIONS 054。
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

/**
 * 通知类型 → 中文标签（规格 §30 列举的五个场景）。
 *
 * 键取**小写下划线**形式：后端派发时实际写入的是 `task_assigned` /
 * `task_status_changed`（见 `app/services/task.py` 的 `_dispatch_notification`），
 * 与规格文档里的 `TASK_ASSIGNED` 大写写法不同（§57「以真实契约为准」）。
 * 规格还列了 `TASK_COMMENTED` / `TEAM_INVITED` / `SYSTEM`，后端目前**尚未派发**
 * 这三类——保留映射以便后端接线后自动生效，未知类型由 `notificationTypeLabel`
 * 原样回退，不猜含义。
 */
export const NOTIFICATION_TYPE_LABELS: Record<string, string> = {
  task_assigned: '任务分配',
  task_status_changed: '状态变更',
  task_commented: '任务评论',
  team_invited: '团队邀请',
  system: '系统',
}

/** 类型的中文标签；未知类型原样返回，避免出现错误的语义归类。 */
export function notificationTypeLabel(type: string): string {
  return NOTIFICATION_TYPE_LABELS[type.toLowerCase()] ?? type
}
