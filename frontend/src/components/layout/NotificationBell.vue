<script setup lang="ts">
/**
 * 顶部消息通知（前端规格 §31）。
 *
 * 数据来自 `stores/notification.ts`：铃铛在任何页面都要显示未读数，所以由
 * `AppHeader` 在进入主框架时统一拉一次；这里只负责展示与两个动作（全部已读、
 * 查看全部）。
 *
 * 未读数是**前端统计**的：后端没有 unread-count 端点，`GET /notifications`
 * 返回完整列表项（含 `is_read`），预览只取最近若干条，所以通知超过一屏时角标
 * 会小于真实未读数。这是后端的既有限制，见 `types/notification.ts` 的说明。
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'

import { useNotificationStore } from '@/stores/notification'
import { formatRelativeTime } from '@/utils/format'

const router = useRouter()
const store = useNotificationStore()

const items = computed(() => store.items)
const unreadCount = computed(() => store.unreadCount)

async function handleMarkAllRead(): Promise<void> {
  const marked = await store.markAllRead()
  ElMessage.success(marked > 0 ? `已将 ${marked} 条通知标记为已读` : '没有未读通知')
}

function goToNotifications(): void {
  void router.push({ name: 'notification-list' })
}
</script>

<template>
  <el-popover placement="bottom-end" :width="320" trigger="click">
    <template #reference>
      <el-badge :value="unreadCount" :max="99" :hidden="unreadCount === 0">
        <el-button text class="tf-bell__trigger">
          <el-icon :size="18"><Bell /></el-icon>
        </el-button>
      </el-badge>
    </template>

    <div class="tf-bell__panel">
      <div class="tf-bell__head">
        <span class="tf-bell__title">通知</span>
        <el-button
          text
          type="primary"
          size="small"
          :disabled="unreadCount === 0"
          @click="handleMarkAllRead"
        >
          全部已读
        </el-button>
      </div>

      <el-empty v-if="items.length === 0" description="暂无通知" :image-size="60" />

      <ul v-else class="tf-bell__list">
        <li v-for="item in items" :key="item.id" class="tf-bell__item">
          <span class="tf-bell__dot" :class="{ 'tf-bell__dot--unread': !item.is_read }" />
          <div class="tf-bell__content">
            <p class="tf-bell__item-title">{{ item.title }}</p>
            <p v-if="item.content" class="tf-bell__item-text">{{ item.content }}</p>
            <p class="tf-bell__item-time">{{ formatRelativeTime(item.created_at) }}</p>
          </div>
        </li>
      </ul>

      <div class="tf-bell__foot">
        <el-button text type="primary" size="small" @click="goToNotifications">
          查看全部
        </el-button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.tf-bell__trigger {
  padding: 6px;
}

.tf-bell__panel {
  margin: -12px;
}

.tf-bell__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}

.tf-bell__title {
  font-weight: 600;
}

.tf-bell__list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 280px;
  overflow-y: auto;
}

.tf-bell__item {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-color);
}

.tf-bell__dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background-color: var(--border-strong);
}

.tf-bell__dot--unread {
  background-color: var(--color-danger);
}

.tf-bell__content {
  min-width: 0;
}

.tf-bell__item-title {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--text-primary);
  word-break: break-word;
}

.tf-bell__item-text {
  margin: 4px 0 0;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  word-break: break-word;
}

.tf-bell__item-time {
  margin: 4px 0 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.tf-bell__foot {
  padding: 4px 12px;
  text-align: center;
}
</style>
