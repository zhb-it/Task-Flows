/**
 * 评论 API（前端规格 §28「任务评论」，阶段 9）。
 *
 * 端点对齐 `app/api/v1/comments.py`：
 *
 * | 函数            | 方法   | 端点                                | 功能级权限        |
 * | --------------- | ------ | ----------------------------------- | ----------------- |
 * | `listComments`  | GET    | `/tasks/{task_id}/comments`         | `task:read`       |
 * | `createComment` | POST   | `/tasks/{task_id}/comments`         | `comment:create`  |
 * | `deleteComment` | DELETE | `/comments/{comment_id}`            | `comment:delete`  |
 *
 * ⚠ `DELETE` 的功能级 `comment:delete` 在种子数据里**仅 admin 持有**，且它在资源级
 * 判定（作者本人 / 团队 OWNER/ADMIN）**之前**执行——因此普通成员删除自己的评论也会
 * 被 403 拦截（`docs/FRONTEND_API_MAPPING.md` §4-D11）。前端仍按规格 §28 显示「删除
 * 自己的评论」按钮（数据驱动：`comment.user_id === 当前用户`），越权由后端 403 兜底并
 * 由请求层统一提示，不臆测权限集隐藏按钮（见 DECISIONS 052）。
 *
 * 响应走 `{data, message}` 信封，由 `utils/request.ts` 解包，这里只返回业务数据。
 */

import { http } from '@/utils/request'
import type { Comment, CommentCreate, CommentListParams } from '@/types/comment'

/** `GET /tasks/{task_id}/comments` —— 任务的评论列表（task:read）。 */
function listComments(taskId: number, params?: CommentListParams): Promise<Comment[]> {
  return http.get<Comment[]>(`/tasks/${taskId}/comments`, { params })
}

/** `POST /tasks/{task_id}/comments` —— 发表评论（任务所属团队成员）。 */
function createComment(taskId: number, payload: CommentCreate): Promise<Comment> {
  return http.post<Comment>(`/tasks/${taskId}/comments`, payload)
}

/** `DELETE /comments/{comment_id}` —— 删除评论（作者或团队管理者；后端判定）。 */
function deleteComment(commentId: number): Promise<void> {
  return http.delete<void>(`/comments/${commentId}`)
}

export const commentApi = {
  listComments,
  createComment,
  deleteComment,
}
