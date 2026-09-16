/**
 * 附件 API（前端规格 §29「任务附件」，阶段 10）。
 *
 * 端点对齐 `app/api/v1/attachments.py`：
 *
 * | 函数                 | 方法   | 端点                            | 功能级权限          |
 * | -------------------- | ------ | ------------------------------- | ------------------- |
 * | `listAttachments`    | GET    | `/tasks/{task_id}/attachments`  | `task:read`         |
 * | `uploadAttachment`   | POST   | `/tasks/{task_id}/attachments`  | `attachment:upload` |
 * | `downloadAttachment` | GET    | `/attachments/{id}`             | `attachment:download`|
 * | `deleteAttachment`   | DELETE | `/attachments/{id}`             | `attachment:upload` |
 *
 * ⚠ 上传是 `multipart/form-data`，文件字段名固定 **`file`**；`FormData` **不要**手写
 * `Content-Type`（否则丢 boundary）。后端**按扩展名**判定类型、不采信客户端
 * `Content-Type`，超过 `MAX_UPLOAD_SIZE` 返回 413、扩展名不在白名单返回 415
 * （`docs/FRONTEND_API_MAPPING.md` §4-D13）。
 * ⚠ 下载端点返回**文件流**而非 `{data,message}` 信封，因此走 `http.getBlob`。
 *
 * 前端在 `before-upload` 里按同一口径预检（大小 / 扩展名）仅为「即时反馈」，
 * 真值一律以后端 413/415 为准——预检通过不代表后端一定接受。
 */

import { http } from '@/utils/request'
import type { Attachment } from '@/types/attachment'

/** 上传大小上限：10 MiB，对齐 `app/core/config.py::max_upload_size`。 */
export const MAX_UPLOAD_SIZE = 10 * 1024 * 1024

/**
 * 允许的扩展名白名单，对齐 `app/services/attachment.py::ALLOWED_TYPES`
 * （图片 / 文档 / 压缩包）。**只用于前端预检**，后端是唯一裁决方。
 */
export const ALLOWED_EXTENSIONS: readonly string[] = [
  // 图片
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'bmp',
  // 文档
  'pdf',
  'txt',
  'md',
  'csv',
  'json',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'ppt',
  'pptx',
  // 压缩包
  'zip',
  'gz',
]

/** `accept` 属性值（`el-upload` / `<input file>` 用），形如 `.png,.jpg,…`。 */
export const ACCEPT_ATTR = ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(',')

/** 取小写扩展名（不含点）；无扩展名返回空串。 */
export function fileExtension(name: string): string {
  const dot = name.lastIndexOf('.')
  return dot >= 0 ? name.slice(dot + 1).toLowerCase() : ''
}

/** 预检扩展名是否在白名单内（仅前端反馈，不替代后端）。 */
export function isAllowedFile(name: string): boolean {
  return ALLOWED_EXTENSIONS.includes(fileExtension(name))
}

/** `GET /tasks/{task_id}/attachments` —— 任务的附件列表（task:read）。 */
function listAttachments(taskId: number): Promise<Attachment[]> {
  return http.get<Attachment[]>(`/tasks/${taskId}/attachments`)
}

/**
 * `POST /tasks/{task_id}/attachments` —— 上传（attachment:upload）。
 *
 * `onProgress` 回调 0~100 的百分比用于进度条（规格 §29「显示进度」）。
 */
function uploadAttachment(
  taskId: number,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<Attachment> {
  const form = new FormData()
  // 字段名固定 `file`（D13）；不设置 Content-Type，交由浏览器带 boundary。
  form.append('file', file)
  return http.post<Attachment>(`/tasks/${taskId}/attachments`, form, {
    onUploadProgress: (event) => {
      if (onProgress != null && event.total) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    },
  })
}

/**
 * `GET /attachments/{id}` —— 下载（attachment:download）。
 *
 * 响应是文件流，取回 `Blob` 后用临时 `<a download>` 触发保存；文件名用列表
 * 里已有的 `filename`（后端响应头的 `Content-Disposition` 前端拿不到，因为
 * 走的是 XHR 而非导航）。
 */
async function downloadAttachment(id: number, filename: string): Promise<void> {
  const blob = await http.getBlob(`/attachments/${id}`)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

/** `DELETE /attachments/{id}` —— 删除（上传者或团队管理者，附件:upload）。 */
function deleteAttachment(id: number): Promise<void> {
  return http.delete<void>(`/attachments/${id}`)
}

export const attachmentApi = {
  listAttachments,
  uploadAttachment,
  downloadAttachment,
  deleteAttachment,
}
