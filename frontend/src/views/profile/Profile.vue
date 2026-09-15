<script setup lang="ts">
/**
 * 个人中心（前端规格 §33）。
 *
 * 只实现**后端真实支持**的部分：展示当前用户资料（数据来自 `/users/me`，
 * 由路由守卫在进入主框架时已拉取）与退出登录。
 *
 * 规格 §33 还列了「修改个人信息」「修改密码」，但后端**没有**对应端点——
 * `app/api/v1/users.py` 只有 `GET /users/me`，全仓没有 `PATCH /users/me`
 * 或改密端点。按规格 §57「禁止猜测 API」，这两项以禁用状态呈现并注明原因，
 * 而不是画一个调用不存在接口的表单。
 */

import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

const user = computed(() => auth.currentUser)

async function handleLogout(): Promise<void> {
  try {
    await ElMessageBox.confirm('确定要退出当前账号吗？', '退出登录', {
      type: 'warning',
      confirmButtonText: '退出',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  await auth.logout()
  notifications.reset()
  ElMessage.success('已退出登录')
  await router.replace({ name: 'login' })
}
</script>

<template>
  <div class="tf-page">
    <el-card shadow="never">
      <template #header>
        <span class="tf-profile__title">个人中心</span>
      </template>

      <el-descriptions v-if="user" :column="1" border label-width="120px">
        <el-descriptions-item label="用户名">{{ user.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ user.email }}</el-descriptions-item>
        <el-descriptions-item label="账号状态">
          <el-tag :type="user.is_active ? 'success' : 'danger'" size="small">
            {{ user.is_active ? '正常' : '已禁用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="注册时间">
          {{ formatDateTime(user.created_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="资料更新时间">
          {{ formatDateTime(user.updated_at) }}
        </el-descriptions-item>
      </el-descriptions>

      <el-empty v-else description="未获取到用户信息" />

      <el-alert
        class="tf-profile__alert"
        type="info"
        :closable="false"
        show-icon
        title="修改资料 / 修改密码暂不可用"
        description="后端当前只提供 GET /api/v1/users/me；没有更新资料与改密的端点，因此这两项功能不会先做界面（规格 §57 禁止猜测 API）。"
      />

      <div class="tf-profile__actions">
        <el-button disabled>修改资料</el-button>
        <el-button disabled>修改密码</el-button>
        <el-button type="danger" plain @click="handleLogout">退出登录</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.tf-profile__title {
  font-weight: 600;
}

.tf-profile__alert {
  margin-top: 16px;
}

.tf-profile__actions {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}
</style>
