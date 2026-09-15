/**
 * 与后端共享的基础类型（前端规格 §39 / §40）。
 *
 * 事实来源是 `app/schemas/common.py`，不是规格文档里的示例：
 * 后端的成功信封是 `{"data": ..., "message": "success"}`，**没有** `code` 字段。
 * 错误信封是 `{"detail": ...}`（字符串或 422 的数组），由 `app.main` 的
 * `app_error_handler` 渲染。规格 §40 举例时写的是带 `code` 的信封，
 * 与真实后端不一致——按规格 §57「以真实契约为准」，这里按后端实现定义。
 */

/** 后端 `SuccessResponse[T]`。 */
export interface ApiEnvelope<T> {
  data: T
  message: string
}

/** FastAPI / Pydantic 422 响应体里的单条校验错误。 */
export interface ValidationErrorItem {
  /** 出错位置，例如 `["body", "username"]`。 */
  loc: Array<string | number>
  /** 人类可读的原因。 */
  msg: string
  /** Pydantic 错误类型，例如 `missing` / `string_too_short`。 */
  type: string
}

/** 后端错误信封里的 `detail` 的两种可能形态。 */
export type ErrorDetail = string | ValidationErrorItem[]

/** 后端列表端点统一使用的分页参数（`skip` / `limit`，`limit <= 100`）。 */
export interface PaginationParams {
  skip?: number
  limit?: number
}
