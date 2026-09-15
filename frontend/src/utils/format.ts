/**
 * 展示层格式化工具（前端规格 §4 的 `utils/format.ts`）。
 *
 * 只做「后端原样数据 → 人类可读文本」，不含业务判断。
 */

/**
 * 把后端返回的 ISO 8601 时间串格式化为本地时间文本。
 *
 * 后端返回的是 Pydantic `datetime` 的序列化结果，可能带时区偏移
 * （`2026-09-15T05:00:00+00:00`）也可能不带。不带时 `new Date()` 会按**浏览器
 * 本地时区**解释，这与后端实际存储的 UTC 值可能不一致——所以这里不擅自补时区，
 * 只在解析失败时退化为原样返回，避免显示出一个错误的精确时间。
 */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

/** 相对时间（「3 分钟前」），用于通知列表这类需要新鲜感的地方。 */
export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (diffSeconds < 60) {
    return '刚刚'
  }
  if (diffSeconds < 3600) {
    return `${Math.floor(diffSeconds / 60)} 分钟前`
  }
  if (diffSeconds < 86400) {
    return `${Math.floor(diffSeconds / 3600)} 小时前`
  }
  if (diffSeconds < 604800) {
    return `${Math.floor(diffSeconds / 86400)} 天前`
  }
  return formatDateTime(value)
}
