/**
 * 通知 API（前端规格 §30 / §31）。
 *
 * 对齐 `app/api/v1/notifications.py`：
 *
 * | 函数                       | 端点                              |
 * | -------------------------- | --------------------------------- |
 * | `listNotifications`        | `GET   /notifications`            |
 * | `markAllNotificationsRead` | `PATCH /notifications/read-all`   |
 * | `markNotificationRead`     | `PATCH /notifications/{id}/read`  |
 *
 * 全部端点**只要求认证**，不要求功能级权限（通知是用户私有收件箱）。
 * 列表参数是后端的 `skip` / `limit`（`limit` 上限 100），没有「未读筛选」参数，
 * 未读数由前端自行统计。
 */

import { http } from '@/utils/request'
import type { PaginationParams } from '@/types/common'
import type { Notification, NotificationMarkAllRead } from '@/types/notification'

/** `GET /notifications` —— 当前用户自己的通知，最新在前。 */
function listNotifications(params?: PaginationParams): Promise<Notification[]> {
  return http.get<Notification[]>('/notifications', { params })
}

/** `PATCH /notifications/read-all` —— 全部标记已读，返回真正翻转的条数。 */
function markAllNotificationsRead(): Promise<NotificationMarkAllRead> {
  return http.patch<NotificationMarkAllRead>('/notifications/read-all')
}

/** `PATCH /notifications/{id}/read` —— 标记一条已读（非本人 → 404）。 */
function markNotificationRead(notificationId: number): Promise<Notification> {
  return http.patch<Notification>(`/notifications/${notificationId}/read`)
}

export const notificationApi = {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
}
