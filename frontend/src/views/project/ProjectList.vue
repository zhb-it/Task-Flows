<script setup lang="ts">
/** 项目列表（前端规格 §16.1 / 阶段 7）。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { FolderOpened, Search } from '@element-plus/icons-vue'

import { projectApi } from '@/api/project'
import { teamApi } from '@/api/team'
import type { Project, ProjectCreate } from '@/types/project'
import type { Team } from '@/types/team'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import EmptyState from '@/components/common/EmptyState.vue'

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

/**
 * 是否处于「筛选后」状态。空态文案必须区分这两种情况（TASK-130）：旧版把
 * 它们合成一句「还没有项目，或筛选无匹配」，用户无法判断是数据没了还是自己
 * 的筛选条件太严，也就不知道该点「创建项目」还是「清除筛选」。
 */
const hasFilter = computed(() => keyword.value.trim() !== '' || teamFilter.value !== '')

function resetFilters(): void {
  keyword.value = ''
  teamFilter.value = ''
}

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
        <p class="page-sub">管理你所在团队下的项目。</p>
      </div>
      <el-button type="primary" :disabled="teams.length === 0" @click="openCreate">
        创建项目
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="部分能力即将上线"
      description="项目卡片暂不展示成员数、任务数与进度，也不支持按状态筛选——这些能力将在后续版本提供。当前支持按名称或描述搜索、按团队筛选。"
    />

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="按名称或描述搜索"
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
      <EmptyState
        v-if="!loading && filteredProjects.length === 0"
        class="card-grid__empty"
        :icon="hasFilter ? Search : FolderOpened"
        :title="hasFilter ? '没有匹配的项目' : '还没有项目'"
        :description="
          hasFilter
            ? '当前搜索/团队筛选下没有结果。数据还在，换个条件或清空筛选就能看到。'
            : teams.length === 0
              ? '项目必须挂在团队下。先去建一个团队，再回来建项目。'
              : '建立项目后，就可以在里面拆任务、分配负责人了。'
        "
      >
        <template #actions>
          <el-button v-if="hasFilter" @click="resetFilters">清除筛选</el-button>
          <el-button v-else-if="teams.length === 0" type="primary" @click="router.push('/teams')">
            先去建团队
          </el-button>
          <el-button v-else type="primary" @click="openCreate">创建项目</el-button>
        </template>
      </EmptyState>
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
/* 空态占据整个网格宽度：否则它会缩在 280px 的第一列里，看起来像一张空卡片。 */
.card-grid__empty {
  grid-column: 1 / -1;
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
