/**
 * 附件类型（前端规格 §29「任务附件」，阶段 10）。
 *
 * 对齐 `app/schemas/attachment.py::AttachmentRead`：
 * `{id, task_id, uploader_id, uploader, filename, content_type, size, created_at}`
 * （`uploader` 内嵌，直接渲染上传者名，不额外查用户）。
 *
 * 上传走 `multipart/form-data`（文件字段名固定 `file`），入站约束在 Service 层
 * 按块累计实现，**没有**对应的 Pydantic 请求体模型，因此这里也没有 `AttachmentCreate`。
 *
 * 字段名保持后端 snake_case（规格 §37），不做驼峰转换。
 */

/** 附件（对齐 `AttachmentRead`）。 */
export interface Attachment {
  id: number
  task_id: number
  uploader_id: number
  uploader: string
  filename: string
  content_type: string
  size: number
  created_at: string
}
