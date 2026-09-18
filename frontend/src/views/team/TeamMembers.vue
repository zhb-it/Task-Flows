<script setup lang="ts">
/** 团队成员管理（前端规格 §14 / §15 / 阶段 6）。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { permissionApi } from '@/api/permission'
import { teamApi } from '@/api/team'
import type { TeamMember, TeamMemberInvite, TeamRole } from '@/types/team'
import type { UserWithRoles } from '@/types/permission'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ teamId: string }>()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const members = ref<TeamMember[]>([])
const teamIdNum = computed(() => Number(props.teamId))

const currentRole = computed<TeamRole | null>(() => {
  const uid = authStore.currentUser?.id
  if (uid == null) return null
  return members.value.find((m) => m.user_id === uid)?.role ?? null
})
/** 邀请 / 移除成员需要 OWNER 或 ADMIN（后端 team:invite 权限的归属）。 */
const canManage = computed(() => currentRole.value === 'owner' || currentRole.value === 'admin')

const roleTag: Record<TeamRole, 'success' | 'warning' | 'info'> = {
  owner: 'warning',
  admin: 'success',
  member: 'info',
}
const roleLabel: Record<TeamRole, string> = { owner: '创建者', admin: '管理员', member: '成员' }

async function loadMembers(): Promise<void> {
  loading.value = true
  try {
    members.value = await teamApi.listMembers(teamIdNum.value)
  } catch {
    // 404（非成员）由请求层提示。
  } finally {
    loading.value = false
  }
}

// --- 邀请成员（按 user_id 邀请；选择器解决「不知道 id 对应谁」，TASK-086） --------
const inviteVisible = ref(false)
const inviting = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<TeamMemberInvite>({ user_id: undefined as unknown as number, role: 'member' })
const rules: FormRules<TeamMemberInvite> = {
  user_id: [{ required: true, message: '请选择要邀请的用户', trigger: 'change' }],
}

/** 候选用户：对话框打开时预载前 50 个，输入关键词后远程搜索（后端 /users?q=）。 */
const userOptions = ref<UserWithRoles[]>([])
const searchingUsers = ref(false)

async function searchUsers(query: string): Promise<void> {
  searchingUsers.value = true
  try {
    userOptions.value = await permissionApi.listUsers(0, 50, query.trim() || undefined)
  } catch {
    // 加载失败清空候选即可：请求层已统一提示，选择器保持可用。
    userOptions.value = []
  } finally {
    searchingUsers.value = false
  }
}

function openInvite(): void {
  form.user_id = undefined as unknown as number
  form.role = 'member'
  formRef.value?.clearValidate()
  inviteVisible.value = true
  // 打开即预载候选，管理员不必先猜关键词。
  void searchUsers('')
}

async function submitInvite(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    inviting.value = true
    try {
      await teamApi.inviteMember(teamIdNum.value, { user_id: Number(form.user_id), role: form.role })
      ElMessage.success('已发送邀请')
      inviteVisible.value = false
      await loadMembers()
    } catch {
      // 404（用户不存在）/ 409（已是成员）/ 422（role=owner）由请求层提示。
    } finally {
      inviting.value = false
    }
  })
}

async function removeMember(m: TeamMember): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定将「${m.username}」移出团队吗？`,
      '移除成员',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  try {
    await teamApi.removeMember(teamIdNum.value, m.user_id)
    ElMessage.success('已移除该成员')
    await loadMembers()
  } catch {
    // 403（层级不足 / owner 不可移除）/ 404 由请求层提示。
  }
}

onMounted(loadMembers)
</script>

<template>
  <div v-loading="loading" class="team-members">
    <el-button link @click="router.push({ name: 'team-detail', params: { teamId: props.teamId } })">
      ← 返回团队详情
    </el-button>
    <div class="header-row">
      <h2 class="title">成员管理（{{ members.length }}）</h2>
      <el-button v-if="canManage" type="primary" @click="openInvite">邀请成员</el-button>
    </div>

    <el-table :data="members" empty-text="暂无成员" stripe>
      <el-table-column prop="username" label="用户" min-width="140" />
      <el-table-column label="角色" width="120">
        <template #default="{ row }">
          <el-tag :type="roleTag[row.role as TeamRole]" size="small">
            {{ roleLabel[row.role as TeamRole] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="加入时间" width="180">
        <template #default="{ row }">{{ formatDateTime(row.joined_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="canManage && row.role !== 'owner'"
            link
            type="danger"
            @click="removeMember(row as TeamMember)"
          >
            移除
          </el-button>
          <span v-else-if="row.role === 'owner'" class="muted">创建者</span>
        </template>
      </el-table-column>
    </el-table>

    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="成员管理说明"
      description="成员列表仅显示用户名；如需调整成员角色，可先将其移出团队再重新邀请；邀请时支持按用户名或邮箱搜索后选定；团队创建者（Owner）不可被邀请或移除。"
      style="margin-top: 16px"
    />

    <el-dialog v-model="inviteVisible" title="邀请成员" width="440px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="用户" prop="user_id">
          <el-select
            v-model="form.user_id"
            filterable
            remote
            clearable
            :remote-method="searchUsers"
            :loading="searchingUsers"
            placeholder="输入用户名或邮箱搜索"
            style="width: 100%"
          >
            <el-option
              v-for="u in userOptions"
              :key="u.id"
              :label="`${u.username}（${u.email}）`"
              :value="u.id"
            >
              <span class="invite-option">
                <span class="invite-option__name">{{ u.username }}</span>
                <span class="invite-option__meta">#{{ u.id }} · {{ u.email }}</span>
              </span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%">
            <el-option label="成员" value="member" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="inviteVisible = false">取消</el-button>
        <el-button type="primary" :loading="inviting" @click="submitInvite">邀请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.team-members {
  padding: 4px;
}
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 8px 0 16px;
}
.title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.invite-option {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}
.invite-option__meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
</style>
