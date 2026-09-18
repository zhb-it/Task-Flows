<script setup lang="ts">
/** 团队详情（前端规格 §13 / 阶段 6）。 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { teamApi } from '@/api/team'
import { projectApi } from '@/api/project'
import type { Team, TeamUpdate, TeamMember } from '@/types/team'
import type { Project } from '@/types/project'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ teamId: string }>()
const router = useRouter()
const authStore = useAuthStore()

const loading = ref(false)
const notFound = ref(false)
const team = ref<Team | null>(null)
const members = ref<TeamMember[]>([])
const projects = ref<Project[]>([])

const teamIdNum = computed(() => Number(props.teamId))

/** 当前用户在团队中的角色（从成员列表读取，数据驱动，不猜权限集合，见 FRONTEND_API_MAPPING §4-D4）。 */
const currentRole = computed<TeamMember['role'] | null>(() => {
  const uid = authStore.currentUser?.id
  if (uid == null) return null
  return members.value.find((m) => m.user_id === uid)?.role ?? null
})
const isOwner = computed(() => currentRole.value === 'owner')
const ownerName = computed(
  () => members.value.find((m) => m.role === 'owner')?.username ?? `ID ${team.value?.owner_id ?? '?'}`,
)

async function loadDetail(): Promise<void> {
  loading.value = true
  notFound.value = false
  try {
    const [t, ms, ps] = await Promise.all([
      teamApi.getTeam(teamIdNum.value),
      teamApi.listMembers(teamIdNum.value),
      projectApi.listProjects({ limit: 100 }),
    ])
    team.value = t
    members.value = ms
    // 后端没有「按团队筛项目」的端点，这里在已返回的列表上按 team_id 过滤
    // （GET /projects 本身只返回「我参与的团队下的项目」）。
    projects.value = ps.filter((p) => p.team_id === teamIdNum.value)
  } catch (err) {
    const anyErr = err as { status?: number }
    if (anyErr?.status === 404) {
      notFound.value = true
    }
    // 其余错误由请求层统一提示。
  } finally {
    loading.value = false
  }
}

// --- 编辑团队（仅 owner） --------------------------------------------------
const editVisible = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<TeamUpdate>({ name: '', description: '' })
const rules: FormRules<TeamUpdate> = {
  name: [{ required: true, message: '请输入团队名称', trigger: 'blur' }],
}

function openEdit(): void {
  if (!team.value) return
  form.name = team.value.name
  form.description = team.value.description ?? ''
  formRef.value?.clearValidate()
  editVisible.value = true
}

async function submitEdit(): Promise<void> {
  if (!formRef.value || !team.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      const updated = await teamApi.updateTeam(team.value!.id, {
        name: form.name,
        description: form.description || null,
      })
      team.value = updated
      ElMessage.success('团队信息已更新')
      editVisible.value = false
    } catch {
      // 404（非 owner）/ 422 由请求层提示。
    } finally {
      saving.value = false
    }
  })
}

watch(() => props.teamId, loadDetail)
onMounted(loadDetail)
</script>

<template>
  <div v-loading="loading" class="team-detail">
    <el-button link @click="router.push({ name: 'team-list' })">← 返回团队列表</el-button>

    <el-empty v-if="notFound" description="团队不存在，或你不在该团队的成员列表中" />

    <template v-else-if="team">
      <div class="header-row">
        <div>
          <h2 class="title">{{ team.name }}</h2>
          <p class="desc">{{ team.description || '暂无描述' }}</p>
        </div>
        <el-button v-if="isOwner" @click="openEdit">团队设置</el-button>
      </div>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="任务统计即将上线"
        description="团队维度的任务总数与状态分布正在建设中，上线后此处会自动展示。"
        style="margin-bottom: 16px"
      />

      <el-row :gutter="16">
        <el-col :span="8">
          <el-card shadow="never">
            <template #header>基本信息</template>
            <ul class="meta">
              <li><span>创建者</span><b>{{ ownerName }}</b></li>
              <li><span>成员数</span><b>{{ members.length }}</b></li>
              <li><span>项目数</span><b>{{ projects.length }}</b></li>
              <li><span>创建时间</span><b>{{ formatDateTime(team.created_at) }}</b></li>
            </ul>
            <el-button link type="primary" @click="router.push({ name: 'team-members', params: { teamId: String(team.id) } })">
              管理成员（{{ members.length }}）
            </el-button>
          </el-card>
        </el-col>
        <el-col :span="16">
          <el-card shadow="never">
            <template #header>项目（{{ projects.length }}）</template>
            <el-empty v-if="projects.length === 0" description="该团队下还没有项目" :image-size="80" />
            <ul v-else class="project-list">
              <li v-for="p in projects" :key="p.id">
                <el-link type="primary" @click="router.push({ name: 'project-detail', params: { projectId: String(p.id) } })">
                  {{ p.name }}
                </el-link>
                <span class="muted">{{ p.description || '—' }}</span>
              </li>
            </ul>
          </el-card>
        </el-col>
      </el-row>

      <el-dialog v-model="editVisible" title="团队设置" width="460px">
        <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
          <el-form-item label="名称" prop="name">
            <el-input v-model="form.name" maxlength="150" />
          </el-form-item>
          <el-form-item label="描述">
            <el-input v-model="form.description" type="textarea" :rows="3" maxlength="255" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.team-detail {
  padding: 4px;
}
.header-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin: 8px 0 16px;
}
.title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.desc {
  margin: 0;
  color: var(--el-text-color-secondary);
}
.meta {
  list-style: none;
  padding: 0;
  margin: 0 0 12px;
}
.meta li {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-size: 14px;
}
.meta li span {
  color: var(--el-text-color-secondary);
}
.project-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.project-list li {
  display: flex;
  flex-direction: column;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
