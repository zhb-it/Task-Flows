<script setup lang="ts">
/**
 * 权限管理（TASK-084；前端规格 §34 RBAC 落点 / 后端 TASK-082/083 端点）。
 *
 * 两个区块，按当前用户权限分开展示：
 *
 * 1. **角色-权限矩阵**（`GET /permissions`，需 `user:update`）——只读表格，
 *    回答「admin / member 各能做什么」。member 调用会 403，因此区块以
 *    `can('user:update')` 控制加载，并在无权限时诚实说明（el-alert）。
 * 2. **用户角色管理**（`GET /users` + `PUT /users/{id}/roles`）——列表展示
 *    每个用户的角色，行内编辑。同样仅 `user:update` 可用。
 *
 * 规格纪律（§35）：页面内的 `can()` 只控制「要不要发起管理请求」，不是安全
 * 边界；后端对每个端点都有功能级守卫，越权请求会得到 403。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { permissionApi } from '@/api/permission'
import { usePermission } from '@/composables/usePermission'
import { useAuthStore } from '@/stores/auth'
import type { PermissionMatrixRole, UserWithRoles } from '@/types/permission'
import { formatDateTime } from '@/utils/format'
import { ApiError } from '@/utils/request'

const { can } = usePermission()
const authStore = useAuthStore()
const currentUserId = computed(() => authStore.currentUser?.id ?? -1)

const loading = ref(false)
const matrix = ref<PermissionMatrixRole[]>([])
const users = ref<UserWithRoles[]>([])
const matrixError = ref<string | null>(null)
const usersError = ref<string | null>(null)

/** 用户列表搜索关键词（回车/按钮触发；后端 /users?q= 子串匹配，TASK-085/086）。 */
const userKeyword = ref('')
const userSearching = ref(false)

/** 角色中文名（后端 description 是英文种子文案，界面用固定映射更好读）。 */
const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  member: '普通成员',
}

function roleLabel(name: string): string {
  return ROLE_LABELS[name] ?? name
}

function describeError(error: unknown): string {
  return error instanceof ApiError ? error.message : '请求失败，请稍后重试'
}

/** 是否可编辑该行角色：需要 user:update，且不能改自己（后端同样禁止）。 */
function editable(row: UserWithRoles): boolean {
  const me = currentUserId.value
  return can('user:update') && row.id !== me
}

// --- 角色编辑 ---------------------------------------------------------------

const editorVisible = ref(false)
const editorSaving = ref(false)
const editorUser = ref<UserWithRoles | null>(null)
const editorRoles = ref<string[]>([])

const ALL_ROLES = ['admin', 'member'] as const

function openEditor(row: UserWithRoles): void {
  editorUser.value = row
  editorRoles.value = [...row.roles]
  editorVisible.value = true
}

async function saveEditor(): Promise<void> {
  if (!editorUser.value) return
  editorSaving.value = true
  try {
    const result = await permissionApi.replaceUserRoles(editorUser.value.id, {
      roles: editorRoles.value,
    })
    editorUser.value.roles = result.roles
    ElMessage.success('角色已更新')
    editorVisible.value = false
  } catch (error) {
    ElMessage.error(describeError(error))
  } finally {
    editorSaving.value = false
  }
}

// --- 数据加载 ---------------------------------------------------------------

async function loadMatrix(): Promise<void> {
  matrixError.value = null
  try {
    matrix.value = await permissionApi.fetchMatrix()
  } catch (error) {
    matrixError.value = describeError(error)
  }
}

async function loadUsers(): Promise<void> {
  usersError.value = null
  userSearching.value = true
  try {
    users.value = await permissionApi.listUsers(0, 100, userKeyword.value.trim() || undefined)
  } catch (error) {
    usersError.value = describeError(error)
  } finally {
    userSearching.value = false
  }
}

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    if (can('user:update')) {
      await Promise.all([loadMatrix(), loadUsers()])
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<template>
  <div v-loading="loading" class="tf-perm">
    <h2 class="tf-perm__title">权限管理</h2>

    <el-alert
      v-if="!can('user:update')"
      type="info"
      :closable="false"
      show-icon
      title="当前账号没有管理权限"
      description="权限矩阵与用户角色管理仅对管理员（持有 user:update 权限）开放。如需调整，请联系管理员。"
      class="tf-perm__alert"
    />

    <template v-else>
      <el-card shadow="never" class="tf-perm__card">
        <template #header>角色-权限矩阵</template>
        <el-alert
          v-if="matrixError"
          type="warning"
          :closable="false"
          show-icon
          :title="`权限矩阵加载失败：${matrixError}`"
        />
        <el-table v-else :data="matrix" border>
          <el-table-column prop="name" label="角色" width="140">
            <template #default="{ row }">
              <el-tag :type="(row as PermissionMatrixRole).name === 'admin' ? 'danger' : 'info'">
                {{ roleLabel((row as PermissionMatrixRole).name) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="说明" min-width="220" />
          <el-table-column label="权限（resource:action）" min-width="420">
            <template #default="{ row }">
              <el-tag
                v-for="perm in (row as PermissionMatrixRole).permissions"
                :key="perm"
                size="small"
                class="tf-perm__tag"
              >
                {{ perm }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-card shadow="never" class="tf-perm__card">
        <template #header>
          <div class="tf-perm__card-header">
            <span>用户角色</span>
            <div class="tf-perm__search">
              <el-input
                v-model="userKeyword"
                clearable
                placeholder="按用户名 / 邮箱搜索"
                style="width: 220px"
                @keyup.enter="loadUsers"
                @clear="loadUsers"
              />
              <el-button type="primary" plain :loading="userSearching" @click="loadUsers">
                搜索
              </el-button>
              <el-button text type="primary" @click="loadUsers">刷新</el-button>
            </div>
          </div>
        </template>
        <el-alert
          v-if="usersError"
          type="warning"
          :closable="false"
          show-icon
          :title="`用户列表加载失败：${usersError}`"
        />
        <el-table v-else :data="users" border>
          <el-table-column prop="username" label="用户名" min-width="140" />
          <el-table-column prop="email" label="邮箱" min-width="200" />
          <el-table-column label="角色" min-width="160">
            <template #default="{ row }">
              <el-tag
                v-for="role in (row as UserWithRoles).roles"
                :key="role"
                size="small"
                :type="role === 'admin' ? 'danger' : 'info'"
                class="tf-perm__tag"
              >
                {{ roleLabel(role) }}
              </el-tag>
              <span v-if="(row as UserWithRoles).roles.length === 0" class="tf-perm__muted">
                （无角色）
              </span>
            </template>
          </el-table-column>
          <el-table-column label="注册时间" width="180">
            <template #default="{ row }">
              {{ formatDateTime((row as UserWithRoles).created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="editable(row as UserWithRoles)"
                size="small"
                type="primary"
                text
                @click="openEditor(row as UserWithRoles)"
              >
                分配角色
              </el-button>
              <span v-else class="tf-perm__muted">本人</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <el-dialog v-model="editorVisible" title="分配角色" width="420px">
        <p v-if="editorUser" class="tf-perm__editor-user">
          为 <strong>{{ editorUser.username }}</strong> 选择角色（全量替换）：
        </p>
        <el-checkbox-group v-model="editorRoles">
          <el-checkbox v-for="role in ALL_ROLES" :key="role" :value="role">
            {{ roleLabel(role) }}
          </el-checkbox>
        </el-checkbox-group>
        <template #footer>
          <el-button @click="editorVisible = false">取消</el-button>
          <el-button type="primary" :loading="editorSaving" @click="saveEditor">
            保存
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.tf-perm__title {
  margin: 0 0 16px;
  font-size: 18px;
  color: var(--text-primary);
}

.tf-perm__alert {
  margin-bottom: 16px;
}

.tf-perm__card {
  margin-bottom: 16px;
}

.tf-perm__card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tf-perm__search {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tf-perm__tag {
  margin-right: 6px;
  margin-bottom: 4px;
}

.tf-perm__muted {
  color: var(--text-tertiary);
  font-size: 12px;
}

.tf-perm__editor-user {
  margin: 0 0 12px;
  color: var(--text-secondary);
}
</style>
