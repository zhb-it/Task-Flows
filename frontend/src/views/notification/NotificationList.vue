<script setup lang="ts">
/**
 * 通知列表（前端规格 §30 / §31，阶段 11）。
 *
 * 接 `app/api/v1/notifications.py` 的三个真实端点：
 * - `GET   /notifications?skip=&limit=`  列表（最新在前）
 * - `PATCH /notifications/read-all`      全部标记已读（返回真正翻转条数）
 * - `PATCH /notifications/{id}/read`     单条标记已读（非本人 → 404）
 *
 * 诚实降级（对应 `docs/FRONTEND_API_MAPPING.md` §4-D9）：
 * - **「全部 / 未读 / 已读」三个页签是客户端过滤**：后端没有 `is_read` 查询参数，
 *   只能把当前页拉回来后在前端筛。
 * - **「点击通知跳转对应资源」（规格 §30）不实现**：`NotificationRead` 没有
 *   link / resource_id 字段，资源编号只以文本形式出现在 `content` 里。前端不解析
 *   正文字符串猜资源 id（会与后端文案强耦合，且 `team_invited` 等类型无 id 可解析），
 *   顶部 `el-alert` 已明示，见 DECISIONS 054。
 * - **分页只有 skip/limit，响应里没有总数**：只能做「上一页 / 下一页」。
 *
 * 标记已读走 `stores/notification.ts`：顶栏铃铛与列表页共享同一份后端数据，
 * 由 store 负责同步，避免「列表里点已读、铃铛角标不变」的不一致。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Check, CircleCheck } from '@element-plus/icons-vue'

import { notificationApi } from '@/api/notification'
import { useNotificationStore } from '@/stores/notification'
import { formatDateTime, formatRelativeTime } from '@/utils/format'
import { notificationTypeLabel, type Notification } from '@/types/notification'
import EmptyState from '@/components/common/EmptyState.vue'

type TabKey = 'all' | 'unread' | 'read'

/** 后端 `limit` 上限为 100（`app/api/v1/notifications.py` 的 `le=100`）。 */
const PAGE_SIZE = 100

const router = useRouter()
const notificationStore = useNotificationStore()

const loading = ref(false)
const notifications = ref<Notification[]>([])
const activeTab = ref<TabKey>('all')
const skip = ref(0)
/**
 * 上一次取回的是否为满页。
 *
 * 后端不返回总数，无法算出总页数；「满页 = 可能还有下一页」是唯一可用的线索，
 * 会在页码提示里如实说明，不假装知道总数。
 */
const lastPageFull = ref(false)
const markingAll = ref(false)
const markingId = ref<number | null>(null)

const unreadCount = computed(() => notifications.value.filter((item) => !item.is_read).length)

const visibleNotifications = computed(() => {
  if (activeTab.value === 'unread') {
    return notifications.value.filter((item) => !item.is_read)
  }
  if (activeTab.value === 'read') {
    return notifications.value.filter((item) => item.is_read)
  }
  return notifications.value
})

/**
 * 空态文案按当前 Tab 分流（TASK-130）：三个 Tab 的空含义完全不同——「全部为空」
 * 是「还没有任何通知」，「未读为空」其实是好事，「已读为空」只是还没处理过。
 * 用同一句「暂无通知」会让人以为通知功能坏了。
 */
const emptyState = computed(() => {
  if (activeTab.value === 'unread') {
    return {
      icon: CircleCheck,
      title: '没有未读通知',
      desc: '收件箱已清空。新的指派、评论与团队邀请会出现在这里。',
    }
  }
  if (activeTab.value === 'read') {
    return {
      icon: Check,
      title: '还没有已读通知',
      desc: '读过的通知会归到这里，方便回看当时发生了什么。',
    }
  }
  return {
    icon: Bell,
    title: '收件箱是空的',
    desc: '任务被指派给你、有人评论、或收到团队邀请时，这里会有第一条通知。',
  }
})

const pageIndex = computed(() => Math.floor(skip.value / PAGE_SIZE) + 1)
const canPrev = computed(() => skip.value > 0)
const canNext = computed(() => lastPageFull.value)

async function load(): Promise<void> {
  loading.value = true
  try {
    const page = await notificationApi.listNotifications({ skip: skip.value, limit: PAGE_SIZE })
    notifications.value = page
    lastPageFull.value = page.length === PAGE_SIZE
  } catch {
    // 错误提示已由请求层统一弹出；列表保持空态。
    notifications.value = []
    lastPageFull.value = false
  } finally {
    loading.value = false
  }
}

function goPrev(): void {
  if (!canPrev.value) return
  skip.value = Math.max(0, skip.value - PAGE_SIZE)
  void load()
}

function goNext(): void {
  if (!canNext.value) return
  skip.value += PAGE_SIZE
  void load()
}

async function markRead(item: Notification): Promise<void> {
  if (item.is_read) return
  markingId.value = item.id
  try {
    // 经 store 调用：store 会用服务端返回的对象更新顶栏铃铛的预览数据。
    await notificationStore.markRead(item.id)
    notifications.value = notifications.value.map((row) =>
      row.id === item.id ? { ...row, is_read: true } : row,
    )
  } catch {
    // 非本人 / 不存在 → 404，提示已由请求层给出。
  } finally {
    markingId.value = null
  }
}

async function markAllRead(): Promise<void> {
  markingAll.value = true
  try {
    const marked = await notificationStore.markAllRead()
    notifications.value = notifications.value.map((row) => ({ ...row, is_read: true }))
    ElMessage.success(marked > 0 ? `已将 ${marked} 条通知标记为已读` : '没有未读通知')
  } catch {
    // 提示已由请求层给出。
  } finally {
    markingAll.value = false
  }
}

/** 通知类型 → `el-tag` 配色；未知类型用中性色，不做语义猜测。 */
function typeTagType(type: string): 'primary' | 'success' | 'info' | 'warning' | 'danger' {
  switch (type.toLowerCase()) {
    case 'task_assigned':
      return 'primary'
    case 'task_status_changed':
      return 'warning'
    case 'task_commented':
      return 'success'
    case 'team_invited':
      return 'info'
    case 'system':
      return 'info'
    default:
      return 'info'
  }
}

onMounted(load)
</script>

<template>
  <div class="notification-list">
    <div class="page-header">
      <div>
        <h2 class="page-title">通知</h2>
        <p class="page-sub">当前账号的通知收件箱，最新在前。</p>
      </div>
      <el-button
        type="primary"
        :loading="markingAll"
        :disabled="unreadCount === 0"
        @click="markAllRead"
      >
        全部标记已读
      </el-button>
    </div>

    <el-alert type="info" :closable="false" show-icon class="degrade-alert">
      <template #title>「点击通知跳转对应资源」（规格 §30）暂不可用</template>
      后端 `NotificationRead` 只有 type / title / content / is_read，<b>没有 link 或资源 id 字段</b>，
      资源编号目前仅作为文本出现在 content 里（如「任务 #123 …」）。前端不解析正文字符串去猜资源 id
      （会与后端文案强耦合，且 team_invited 等类型本就无 id 可解析），因此本页不做跳转；
      待后端补充 link / resource_id 字段后再接线。
    </el-alert>

    <el-tabs v-model="activeTab" class="filter-tabs">
      <el-tab-pane :label="`全部 (${notifications.length})`" name="all" />
      <el-tab-pane :label="`未读 (${unreadCount})`" name="unread" />
      <el-tab-pane :label="`已读 (${notifications.length - unreadCount})`" name="read" />
    </el-tabs>

    <div v-loading="loading" class="notification-body">
      <EmptyState
        v-if="visibleNotifications.length === 0"
        :icon="emptyState.icon"
        :title="emptyState.title"
        :description="emptyState.desc"
      >
        <template #actions>
          <el-button v-if="activeTab === 'read'" @click="activeTab = 'all'">
            看全部通知
          </el-button>
          <el-button v-else type="primary" @click="router.push('/tasks')">
            去处理我的任务
          </el-button>
        </template>
      </EmptyState>

      <ul v-else class="notification-items">
        <li
          v-for="item in visibleNotifications"
          :key="item.id"
          class="notification-item"
          :class="{ 'notification-item--unread': !item.is_read }"
        >
          <div class="notification-item__main">
            <div class="notification-item__head">
              <el-tag :type="typeTagType(item.type)" size="small" effect="light">
                {{ notificationTypeLabel(item.type) }}
              </el-tag>
              <span class="notification-item__title">{{ item.title }}</span>
              <el-tag v-if="!item.is_read" type="danger" size="small" effect="plain">未读</el-tag>
            </div>
            <p v-if="item.content" class="notification-item__content">{{ item.content }}</p>
            <p class="notification-item__meta">
              <span :title="formatDateTime(item.created_at)">
                {{ formatRelativeTime(item.created_at) }}
              </span>
              <span class="notification-item__sep">·</span>
              <span>{{ formatDateTime(item.created_at) }}</span>
            </p>
          </div>

          <div class="notification-item__actions">
            <el-button
              v-if="!item.is_read"
              link
              type="primary"
              :loading="markingId === item.id"
              @click="markRead(item)"
            >
              标记已读
            </el-button>
            <span v-else class="notification-item__flag">已读</span>
          </div>
        </li>
      </ul>
    </div>

    <div class="pager">
      <el-button :disabled="!canPrev" @click="goPrev">上一页</el-button>
      <span class="pager__tip">第 {{ pageIndex }} 页 · 后端无总数，仅「上一页 / 下一页」</span>
      <el-button :disabled="!canNext" @click="goNext">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.notification-list {
  padding: 4px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.page-sub {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.degrade-alert {
  margin-bottom: 8px;
}
.filter-tabs {
  margin-bottom: 4px;
}
.notification-body {
  min-height: 160px;
}
.notification-items {
  list-style: none;
  margin: 0;
  padding: 0;
}
.notification-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.notification-item--unread {
  background: var(--el-fill-color-light);
}
.notification-item__main {
  min-width: 0;
}
.notification-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.notification-item__title {
  font-size: 14px;
  color: var(--el-text-color-primary);
  word-break: break-word;
}
.notification-item--unread .notification-item__title {
  font-weight: 600;
}
.notification-item__content {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
  word-break: break-word;
}
.notification-item__meta {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.notification-item__sep {
  margin: 0 6px;
}
.notification-item__actions {
  flex: 0 0 auto;
}
.notification-item__flag {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.pager {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 16px;
}
.pager__tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
