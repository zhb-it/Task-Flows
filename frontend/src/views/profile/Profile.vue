<script setup lang="ts">
/**
 * 个人中心（前端规格 §33 / §69 阶段 12 权限模块的唯一真实落点）。
 *
 * 只实现**后端真实支持**的部分：
 * - 展示当前用户资料（数据来自 `/users/me`，由路由守卫在进入主框架时已拉取）与退出登录；
 * - 「我的团队与角色」（规格 §69 的「用户角色」）：后端 `UserRead` 不含全局角色、
 *   也没有权限集合端点（§4-D4），**唯一能诚实展示的角色数据是各团队内的
 *   `owner|admin|member`**（`GET /teams` + `GET /teams/{id}/members` 数据驱动）。
 *
 * 规格 §33 还列了「修改个人信息」「修改密码」，但后端**没有**对应端点——
 * `app/api/v1/users.py` 只有 `GET /users/me`，全仓没有 `PATCH /users/me`
 * 或改密端点。按规格 §57「禁止猜测 API」，这两项以禁用状态呈现并注明原因，
 * 而不是画一个调用不存在接口的表单。
 */

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAuthStore } from '@/stores/auth'
import { useNotificationStore } from '@/stores/notification'
import { teamApi } from '@/api/team'
import type { Team } from '@/types/team'
import type { TeamRole } from '@/types/team'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const auth = useAuthStore()
const notifications = useNotificationStore()

const user = computed(() => auth.currentUser)

// —— 我的团队与角色（规格 §69「用户角色」按团队落地的唯一诚实形态）——
/** 每个团队一行；`role: null` 表示该团队的成员列表拉取失败或其中没找到自己。 */
interface TeamRoleRow {
  team: Team
  role: TeamRole | null
}

const teamRoles = ref<TeamRoleRow[]>([])
const teamRolesLoading = ref(false)

async function loadTeamRoles(): Promise<void> {
  const me = auth.currentUser
  if (!me) return
  teamRolesLoading.value = true
  try {
    const teams = await teamApi.listTeams({ limit: 100 })
    // 每个团队独立拉成员并独立容错：某一个团队失败只让那一行显示「未知」，
    // 不连累其余团队（与任务详情页评论/附件区块的独立加载模式一致）。
    const rows = await Promise.all(
      teams.map(async (team): Promise<TeamRoleRow> => {
        try {
          const members = await teamApi.listMembers(team.id)
          const mine = members.find((m) => m.user_id === me.id)
          return { team, role: mine?.role ?? null }
        } catch {
          return { team, role: null }
        }
      }),
    )
    teamRoles.value = rows
  } catch {
    // 错误提示已由请求层统一弹出；区块保持空态。
    teamRoles.value = []
  } finally {
    teamRolesLoading.value = false
  }
}

function roleLabel(role: TeamRole | null): string {
  if (role === 'owner') return 'Owner'
  if (role === 'admin') return 'Admin'
  if (role === 'member') return 'Member'
  return '未知'
}

function roleTagType(role: TeamRole | null): 'danger' | 'warning' | 'info' {
  if (role === 'owner') return 'danger'
  if (role === 'admin') return 'warning'
  return 'info'
}

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

onMounted(loadTeamRoles)
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

      <el-divider content-position="left">我的团队与角色</el-divider>
      <p class="tf-profile__team-hint">
        后端不暴露全局角色与权限集合（FRONTEND_API_MAPPING §4-D4），角色只能按团队展示——
        以下是你在各团队中的实际角色（GET /teams + GET /teams/{id}/members 数据驱动）。
      </p>
      <div v-loading="teamRolesLoading" class="tf-profile__teams">
        <el-empty v-if="teamRoles.length === 0" description="尚未加入任何团队" :image-size="60" />
        <ul v-else class="tf-profile__team-list">
          <li v-for="row in teamRoles" :key="row.team.id" class="tf-profile__team-row">
            <span class="tf-profile__team-name">{{ row.team.name }}</span>
            <el-tag :type="roleTagType(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
          </li>
        </ul>
      </div>

      <el-alert
        class="tf-profile__alert"
        type="info"
        :closable="false"
        show-icon
        title="修改资料 / 修改密码即将上线"
        description="这两项功能正在建设中，上线后即可在此使用。"
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

.tf-profile__team-hint {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.tf-profile__teams {
  min-height: 60px;
}

.tf-profile__team-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.tf-profile__team-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.tf-profile__team-name {
  font-size: 14px;
  color: var(--el-text-color-primary);
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
