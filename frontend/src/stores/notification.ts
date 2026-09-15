/**
 * 通知状态（前端规格 §31 顶部消息通知）。
 *
 * 为什么通知进 store：顶栏铃铛在任何页面都要显示未读数，属于「跨页面共享的
 * 小型状态」（规格 §51 允许的范畴）。但**不做长期缓存**（规格 §52 明确通知
 * 列表需要保持较高新鲜度），每次打开面板或进入通知页都重新拉取。
 *
 * 未读数只能由前端统计：后端没有 unread-count 端点，`GET /notifications`
 * 返回的是完整列表项（含 `is_read`）。
 */

import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { notificationApi } from '@/api/notification'
import type { Notification } from '@/types/notification'

/** 顶栏铃铛最多展示的条数。 */
export const NOTIFICATION_PREVIEW_LIMIT = 5

export const useNotificationStore = defineStore('notification', () => {
  /** 已取回的通知（预览用，最新在前）。 */
  const items = ref<Notification[]>([])

  const loading = ref(false)

  const unreadCount = computed(() => items.value.filter((item) => !item.is_read).length)

  /**
   * 拉取通知预览。
   *
   * 用 `silent` 关闭统一错误提示：铃铛是布局的一部分，它失败时弹一个错误框会
   * 在每次进页面都骚扰用户，而通知本身不是阻断性功能。
   */
  async function loadPreview(limit: number = NOTIFICATION_PREVIEW_LIMIT): Promise<void> {
    loading.value = true
    try {
      items.value = await notificationApi.listNotifications({ limit })
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }

  /** 全部标记已读（后端返回真正翻转的条数）。 */
  async function markAllRead(): Promise<number> {
    const result = await notificationApi.markAllNotificationsRead()
    items.value = items.value.map((item) => ({ ...item, is_read: true }))
    return result.marked
  }

  /** 标记单条已读，并用服务端返回的最新对象替换本地项。 */
  async function markRead(notificationId: number): Promise<void> {
    const updated = await notificationApi.markNotificationRead(notificationId)
    items.value = items.value.map((item) => (item.id === notificationId ? updated : item))
  }

  /** 退出登录时清空，避免下一个用户看到上一个用户的通知。 */
  function reset(): void {
    items.value = []
  }

  return { items, loading, unreadCount, loadPreview, markAllRead, markRead, reset }
})
