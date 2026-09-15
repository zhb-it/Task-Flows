<script setup lang="ts">
/**
 * 顶栏（前端规格 §6 / §61）。
 *
 * 三块内容：折叠按钮、右侧的用户菜单与通知铃铛。
 *
 * 折叠状态由布局层（`BasicLayout`）持有，这里只通过 `props` 读、通过事件请求切换
 * ——子组件不直接改父组件的状态。
 */

import { onMounted } from 'vue'
import { Expand, Fold } from '@element-plus/icons-vue'

import NotificationBell from '@/components/layout/NotificationBell.vue'
import UserMenu from '@/components/layout/UserMenu.vue'
import { useNotificationStore } from '@/stores/notification'

const props = defineProps<{ collapsed: boolean }>()

const emit = defineEmits<{ 'toggle-sidebar': [] }>()

const notifications = useNotificationStore()

// 进主框架时拉一次通知预览，让铃铛的未读角标一开始就是对的。
// 失败与否都不影响页面（store 内部静默处理）。
onMounted(() => {
  void notifications.loadPreview()
})
</script>

<template>
  <div class="tf-header">
    <el-button text class="tf-header__toggle" @click="emit('toggle-sidebar')">
      <el-icon :size="18">
        <Expand v-if="props.collapsed" />
        <Fold v-else />
      </el-icon>
    </el-button>

    <div class="tf-header__spacer" />

    <NotificationBell />
    <UserMenu />
  </div>
</template>

<style scoped>
.tf-header {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 16px;
  gap: 8px;
}

.tf-header__toggle {
  padding: 6px;
}

.tf-header__spacer {
  flex: 1;
}
</style>
