<script setup lang="ts">
/**
 * 用户菜单（前端规格 §61 / §33 个人中心）。
 *
 * 退出登录走规格 §44 的二次确认（`ElMessageBox.confirm`），然后调用
 * `authStore.logout()`：先请求后端撤销 Refresh Token，再清本地凭证并跳登录页。
 *
 * 这里同时重置通知 store —— 通知是「上一个用户」的数据，不清空会让下一个登录者
 * 在铃铛里看到别人的通知标题。
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

const displayName = computed(() => auth.currentUser?.username ?? '未登录')
const email = computed(() => auth.currentUser?.email ?? '')
const initial = computed(() => displayName.value.slice(0, 1).toUpperCase())

async function handleLogout(): Promise<void> {
  try {
    await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', {
      type: 'warning',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
  } catch {
    // 用户点了取消：`confirm` 以 reject 表达，不是错误，直接返回。
    return
  }

  await auth.logout()
  notifications.reset()
  ElMessage.success('已退出登录')
  await router.replace({ name: 'login' })
}

function handleCommand(command: string): void {
  if (command === 'profile') {
    void router.push({ name: 'profile' })
    return
  }
  if (command === 'logout') {
    void handleLogout()
  }
}
</script>

<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <span class="tf-user">
      <el-avatar :size="28" class="tf-user__avatar">{{ initial }}</el-avatar>
      <span class="tf-user__name">{{ displayName }}</span>
      <el-icon :size="12"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item disabled>
          <span class="tf-user__email">{{ email }}</span>
        </el-dropdown-item>
        <el-dropdown-item command="profile" divided>个人中心</el-dropdown-item>
        <el-dropdown-item command="logout">退出登录</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.tf-user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: pointer;
  outline: none;
}

.tf-user:hover {
  background-color: #f5f7fa;
}

.tf-user__avatar {
  background-color: #409eff;
  color: #ffffff;
  font-size: 13px;
}

.tf-user__name {
  font-size: 14px;
  color: #303133;
}

.tf-user__email {
  color: #909399;
  font-size: 12px;
}
</style>
