/**
 * `utils/format.ts` 的单元测试（前端规格 §71 单元测试重点「format」）。
 *
 * 时间类函数的断言刻意写得**与时区无关**：`formatDateTime` 的输出依赖运行环境的
 * 本地时区与 ICU，测试只钉住「空值/非法值的降级」与「输出形状」，不钉具体时刻
 * ——否则换一台机器/时区就假失败。相对时间用 `vi.setSystemTime` 固定「现在」，
 * 让各档位边界可精确断言。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { formatDateTime, formatFileSize, formatRelativeTime } from '@/utils/format'

describe('formatDateTime', () => {
  it('空值返回占位符', () => {
    expect(formatDateTime(null)).toBe('-')
    expect(formatDateTime(undefined)).toBe('-')
    expect(formatDateTime('')).toBe('-')
  })

  it('非法时间串原样返回（不擅自补时区）', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date')
  })

  it('合法时间输出「年/月/日 时:分」形状', () => {
    expect(formatDateTime('2026-09-15T05:00:00+00:00')).toMatch(/^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}$/)
  })
})

describe('formatRelativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-16T03:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('空值返回占位符', () => {
    expect(formatRelativeTime(null)).toBe('-')
  })

  it('非法时间串原样返回', () => {
    expect(formatRelativeTime('nope')).toBe('nope')
  })

  it('1 分钟内显示「刚刚」', () => {
    expect(formatRelativeTime('2026-09-16T02:59:30Z')).toBe('刚刚')
  })

  it('1 小时内按分钟计', () => {
    expect(formatRelativeTime('2026-09-16T02:30:00Z')).toBe('30 分钟前')
  })

  it('1 天内按小时计', () => {
    expect(formatRelativeTime('2026-09-16T00:00:00Z')).toBe('3 小时前')
  })

  it('1 周内按天计', () => {
    expect(formatRelativeTime('2026-09-14T03:00:00Z')).toBe('2 天前')
  })

  it('超过 1 周回退为绝对时间', () => {
    expect(formatRelativeTime('2026-09-01T03:00:00Z')).toMatch(/^\d{4}\/\d{2}\/\d{2} \d{2}:\d{2}$/)
  })
})

describe('formatFileSize', () => {
  it('空值与 NaN 返回占位符', () => {
    expect(formatFileSize(null)).toBe('-')
    expect(formatFileSize(undefined)).toBe('-')
    expect(formatFileSize(Number.NaN)).toBe('-')
  })

  it('小于 1 KB 直接显示字节', () => {
    expect(formatFileSize(0)).toBe('0 B')
    expect(formatFileSize(1023)).toBe('1023 B')
  })

  it('KB / MB 按 1024 进制换算，不足 100 保留 1 位小数', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB')
    expect(formatFileSize(1536)).toBe('1.5 KB')
    expect(formatFileSize(10 * 1024 * 1024)).toBe('10.0 MB')
  })

  it('达到 100 以上取整，避免粗糙显示', () => {
    expect(formatFileSize(200 * 1024)).toBe('200 KB')
  })

  it('跨级进位到 GB，且封顶在 TB', () => {
    expect(formatFileSize(5 * 1024 ** 3)).toBe('5.0 GB')
    // 远超 TB：停在 TB 档，不出现「PB」
    expect(formatFileSize(10 * 1024 ** 5)).toMatch(/^\d+(\.\d+)? TB$/)
  })
})
