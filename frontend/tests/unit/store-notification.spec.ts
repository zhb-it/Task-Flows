/**
 * `stores/notification.ts` 的单元测试（前端规格 §71 单元测试重点「stores」）。
 *
 * 钉住的契约：
 * 1. 未读数由前端在**已取回列表**上统计（后端无 unread-count 端点，§4-D9）；
 * 2. 预览请求必须带 `silent: true`——铃铛失败弹窗会在每个页面骚扰用户
 *    （这条曾经是「注释说有、代码没有」的漂移，TASK-075 修正，用例防止回退）;
 * 3. 预览失败静默清空，不向上冒泡；
 * 4. 标记已读后本地列表同步翻转，铃铛与列表共享同一份数据。
 */

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  listNotifications: vi.fn(),
  markAllNotificationsRead: vi.fn(),
  markNotificationRead: vi.fn(),
}))

vi.mock('@/api/notification', () => ({
  notificationApi: mocks,
}))

import { NOTIFICATION_PREVIEW_LIMIT, useNotificationStore } from '@/stores/notification'
import type { Notification } from '@/types/notification'

function makeNotification(id: number, isRead: boolean): Notification {
  return {
    id,
    user_id: 1,
    type: 'task_assigned',
    title: '任务分配',
    content: 'alice 将你分配到任务 #1',
    is_read: isRead,
    created_at: '2026-09-16T03:00:00+00:00',
  }
}

describe('notification store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loadPreview 默认取 5 条并携带 silent（铃铛失败不弹窗）', async () => {
    mocks.listNotifications.mockResolvedValueOnce([makeNotification(1, false)])

    const store = useNotificationStore()
    await store.loadPreview()

    expect(mocks.listNotifications).toHaveBeenCalledWith(
      { limit: NOTIFICATION_PREVIEW_LIMIT },
      { silent: true },
    )
    expect(store.items).toHaveLength(1)
    expect(store.loading).toBe(false)
  })

  it('loadPreview 自定义 limit 透传给 API', async () => {
    mocks.listNotifications.mockResolvedValueOnce([])

    const store = useNotificationStore()
    await store.loadPreview(10)

    expect(mocks.listNotifications).toHaveBeenCalledWith({ limit: 10 }, { silent: true })
  })

  it('loadPreview 失败：静默清空，不向上冒泡', async () => {
    mocks.listNotifications.mockRejectedValueOnce(new Error('network down'))

    const store = useNotificationStore()
    await expect(store.loadPreview()).resolves.toBeUndefined()

    expect(store.items).toEqual([])
    expect(store.loading).toBe(false)
  })

  it('unreadCount 只统计未读条目', () => {
    const store = useNotificationStore()
    store.items = [makeNotification(1, false), makeNotification(2, true), makeNotification(3, false)]

    expect(store.unreadCount).toBe(2)
  })

  it('markAllRead：本地全部翻转为已读，返回后端统计的真实条数', async () => {
    mocks.markAllNotificationsRead.mockResolvedValueOnce({ marked: 2 })

    const store = useNotificationStore()
    store.items = [makeNotification(1, false), makeNotification(2, false), makeNotification(3, true)]
    const marked = await store.markAllRead()

    expect(marked).toBe(2)
    expect(store.items.every((item) => item.is_read)).toBe(true)
    expect(store.unreadCount).toBe(0)
  })

  it('markRead：用服务端返回的最新对象替换本地项', async () => {
    const serverItem = makeNotification(2, true)
    mocks.markNotificationRead.mockResolvedValueOnce(serverItem)

    const store = useNotificationStore()
    store.items = [makeNotification(1, false), makeNotification(2, false)]
    await store.markRead(2)

    expect(mocks.markNotificationRead).toHaveBeenCalledWith(2)
    expect(store.items.find((item) => item.id === 2)?.is_read).toBe(true)
    expect(store.items.find((item) => item.id === 1)?.is_read).toBe(false)
  })

  it('reset：清空列表（退出登录防串号）', () => {
    const store = useNotificationStore()
    store.items = [makeNotification(1, false)]
    store.reset()

    expect(store.items).toEqual([])
    expect(store.unreadCount).toBe(0)
  })
})
