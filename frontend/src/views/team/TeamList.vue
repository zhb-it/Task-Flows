<script setup lang="ts">
/** 团队列表（前端规格 §12 / 阶段 6）。 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { teamApi } from '@/api/team'
import type { Team, TeamCreate } from '@/types/team'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const authStore = useAuthStore()
const currentUserId = computed(() => authStore.currentUser?.id ?? null)

const loading = ref(false)
const teams = ref<Team[]>([])
/** 客户端搜索关键字（后端 GET /teams 没有搜索参数，见 FRONTEND_API_MAPPING §4-D3 同类约束）。 */
const keyword = ref('')

const filteredTeams = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return teams.value
  return teams.value.filter(
    (t) => t.name.toLowerCase().includes(kw) || (t.description ?? '').toLowerCase().includes(kw),
  )
})

async function loadTeams(): Promise<void> {
  loading.value = true
  try {
    teams.value = await teamApi.listTeams({ limit: 100 })
  } catch {
    // 错误提示已由请求层统一弹出；列表保持空态。
  } finally {
    loading.value = false
  }
}

function isOwner(team: Team): boolean {
  return currentUserId.value !== null && team.owner_id === currentUserId.value
}

function openDetail(team: Team): void {
  router.push({ name: 'team-detail', params: { teamId: String(team.id) } })
}

// --- 创建团队 --------------------------------------------------------------
const createVisible = ref(false)
const creating = ref(false)
const formRef = ref<FormInstance>()
const form = reactive<TeamCreate>({ name: '', description: '' })
const rules: FormRules<TeamCreate> = {
  name: [{ required: true, message: '请输入团队名称', trigger: 'blur' }],
}

function openCreate(): void {
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
      const created = await teamApi.createTeam({ ...form })
      ElMessage.success('团队创建成功')
      createVisible.value = false
      // 立即进入详情页，避免成员对「看不到刚建的团队」产生困惑。
      router.push({ name: 'team-detail', params: { teamId: String(created.id) } })
    } catch {
      // 403 表示当前账号没有 team:create（普通 member 会命中）；提示已由请求层给出。
    } finally {
      creating.value = false
    }
  })
}

async function removeTeam(team: Team): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除团队「${team.name}」吗？该操作不可恢复，且会一并删除其下的项目与任务。`,
      '删除团队',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await teamApi.deleteTeam(team.id)
    ElMessage.success('团队已删除')
    await loadTeams()
  } catch {
    // 404（非 owner）/ 403 由请求层提示。
  }
}

onMounted(loadTeams)
</script>

<template>
  <div class="team-list">
    <div class="page-header">
      <div>
        <h2 class="page-title">团队</h2>
        <p class="page-sub">管理你参与的团队。后端只返回「当前用户参与的团队」全量列表（无服务端搜索/分页总数）。</p>
      </div>
      <el-button type="primary" @click="openCreate">创建团队</el-button>
    </div>

    <div class="toolbar">
      <el-input
        v-model="keyword"
        placeholder="按名称或描述搜索（客户端过滤）"
        clearable
        style="max-width: 320px"
      />
      <span class="count-tip">共 {{ filteredTeams.length }} 个团队</span>
    </div>

    <el-table v-loading="loading" :data="filteredTeams" empty-text="还没有加入任何团队" stripe>
      <el-table-column prop="name" label="团队名称" min-width="160">
        <template #default="{ row }">
          <el-link type="primary" @click="openDetail(row)">{{ row.name }}</el-link>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">{{ row.description || '—' }}</template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">查看</el-button>
          <el-button
            v-if="isOwner(row)"
            link
            type="danger"
            @click="removeTeam(row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createVisible" title="创建团队" width="460px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="150" placeholder="团队名称" />
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
.team-list {
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
  margin-bottom: 12px;
}
.count-tip {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
