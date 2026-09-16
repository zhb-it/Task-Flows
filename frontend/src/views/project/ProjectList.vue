<script setup lang="ts">
/** 项目列表（前端规格 §16.1 / 阶段 7）。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { projectApi } from '@/api/project'
import { teamApi } from '@/api/team'
import type { Project, ProjectCreate } from '@/types/project'
import type { Team } from '@/types/team'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const authStore = useAuthStore()
const currentUserId = computed(() => authStore.currentUser?.id ?? null)

const loading = ref(false)
const projects = ref<Project[]>([])
const teams = ref<Team[]>([])
/** 客户端搜索关键字（后端 GET /projects 没有搜索参数，见 FRONTEND_API_MAPPING §4-D3 同类约束）。 */
const keyword = ref('')
/** 客户端团队筛选（用 project.team_id 匹配，后端无 team 查询参数）。 */
const teamFilter = ref<number | ''>('')

const teamNameMap = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const t of teams.value) m[t.id] = t.name
  return m
})

const filteredProjects = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return projects.value.filter((p) => {
    const matchKw =
      !kw || p.name.toLowerCase().includes(kw) || (p.description ?? '').toLowerCase().includes(kw)
    const matchTeam = teamFilter.value === '' || p.team_id === teamFilter.value
    return matchKw && matchTeam
  })
})

async function loadAll(): Promise<void> {
  loading.value = true
  try {
    const [ps, ts] = await Promise.all([
      projectApi.listProjects({ limit: 100 }),
      teamApi.listTeams({ limit: 100 }),
    ])
    projects.value = ps
    teams.value = ts
  } catch {
    // 错误提示已由请求层统一弹出；列表保持空态。
  } finally {
    loading.value = false
  }
}

function openDetail(p: Project): void {
  router.push({ name: 'project-detail', params: { projectId: String(p.id) } })
}

// --- 创建项目 --------------------------------------------------------------
const createVisible = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<ProjectCreate>({ team_id: 0, name: '', description: '' })
const rules: FormRules<ProjectCreate> = {
  team_id: [{ required: true, message: '请选择所属团队', trigger: 'change' }],
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

function openCreate(): void {
  form.team_id = teams.value.length ? teams.value[0].id : 0
  form.name = ''
  form.description = ''
  formRef.value?.clearValidate()
  createVisible.value = true
}

async function submitCreate(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    creating.value = true
    try {
      const created = await projectApi.createProject({ ...form })
      ElMessage.success('项目创建成功')
      createVisible.value = false
      // 直接进入详情页，避免对「看不到刚建的项目」产生困惑。
      router.push({ name: 'project-detail', params: { projectId: String(created.id) } })
    } catch {
      // 403 缺 project:create（普通 member 会命中）；404 团队不存在 / 非成员。
    } finally {
      creating.value = false
    }
  })
}

async function removeProject(p: Project): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除项目「${p.name}」吗？该操作不可恢复，且会一并删除其下的任务。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await projectApi.deleteProject(p.id)
    ElMessage.success('项目已删除')
    await loadAll()
  } catch {
    // 404（非 OWNER/ADMIN）/ 403 由请求层提示。
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="project-list">
    <div class="page-header">
      <div>
        <h2 class="page-title">项目</h2>
        <p class="page-sub">管理你所在团队下的项目。后端列表无服务端搜索 / 状态筛选 / 分页总数，相关能力在客户端降级处理。</p>
      </div>
      <el-button type="primary" :disabled="teams.length === 0" @click="openCreate">
        创建项目
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="后端能力边界（诚实降级，不伪造接口）"
      description="ProjectRead 没有 status 字段，也没有成员数 / 任务数 / 进度字段，因此规格 §16.1 卡片里的「成员：12 / 任务：56 / 78%」与「状态筛选」目前无法展示；搜索与团队筛选为客户端过滤。这些能力需后端新增跨项目统计端点与 project.status 后才可用。"
    />

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="按名称或描述搜索（客户端过滤）"
        clearable
        style="max-width: 320px"
      />
      <el-select
        v-model="teamFilter"
        placeholder="全部团队"
        clearable
        style="max-width: 220px"
      >
        <el-option label="全部团队" :value="''" />
        <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
      <span class="count-tip">共 {{ filteredProjects.length }} 个项目</span>
    </div>

    <div v-loading="loading" class="card-grid">
      <el-empty
        v-if="!loading && filteredProjects.length === 0"
        description="还没有项目，或筛选无匹配"
      />
      <el-card
        v-for="p in filteredProjects"
        :key="p.id"
        class="project-card"
        shadow="hover"
        @click="openDetail(p)"
      >
        <div class="card-head">
          <span class="card-name">{{ p.name }}</span>
          <el-button
            link
            type="danger"
            title="仅团队 Owner / Admin 可删除"
            @click.stop="removeProject(p)"
          >
            删除
          </el-button>
        </div>
        <p class="card-desc">{{ p.description || '暂无描述' }}</p>
        <div class="card-meta">
          <el-tag size="small" effect="plain">{{ teamNameMap[p.team_id] ?? `团队 #${p.team_id}` }}</el-tag>
          <span v-if="currentUserId !== null && p.owner_id === currentUserId" class="owner-tag">我创建</span>
        </div>
        <div class="card-foot">
          <span class="time">{{ formatDateTime(p.created_at) }}</span>
          <el-button type="primary" link @click.stop="openDetail(p)">查看项目 →</el-button>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="createVisible" title="创建项目" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="所属团队" prop="team_id">
          <el-select v-model="form.team_id" placeholder="选择团队" style="width: 100%">
            <el-option v-for="t in teams" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="150" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="255"
            placeholder="选填"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-list {
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
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 16px 0 12px;
}
.count-tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  min-height: 120px;
}
.project-card {
  cursor: pointer;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.card-name {
  font-size: 16px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-desc {
  margin: 8px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  min-height: 38px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.owner-tag {
  font-size: 12px;
  color: var(--el-color-success);
}
.card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 10px;
}
.time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
