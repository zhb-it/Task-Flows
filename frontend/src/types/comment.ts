/**
 * 评论类型（前端规格 §28「任务评论」，阶段 9）。
 *
 * 对齐 `app/schemas/comment.py`：
 *
 * - `CommentRead`：`{id, task_id, user_id, username, content, created_at, updated_at}`
 *   （username 内嵌，供前端直接渲染作者名，不额外查用户）。
 * - `CommentCreate`：仅 `content`（1~2000 字），`task_id` 在路径、`user_id` 取调用者。
 *
 * 字段名保持后端 snake_case（规格 §37），不做驼峰转换。
 */

/** 评论（对齐 `CommentRead`）。 */
export interface Comment {
  id: number
  task_id: number
  user_id: number
  username: string
  content: string
  created_at: string
  updated_at: string
}

/** `POST /tasks/{task_id}/comments` 请求体（对齐 `CommentCreate`）。 */
export interface CommentCreate {
  content: string
}

/** `GET /tasks/{task_id}/comments` 查询参数。 */
export interface CommentListParams {
  skip?: number
  limit?: number
}
