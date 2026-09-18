<script setup lang="ts">
/**
 * 任务列表（前端规格 §20 / 阶段 8）。
 *
 * 后端 `GET /tasks` 的 `project_id` 必填（无默认值，app/api/v1/tasks.py），
 * 因此本页是「按项目查看」的作用域，而非规格 §5 设想的跨项目「我的任务」全局页。
 * 跨项目视图后端暂未提供（docs/FRONTEND_API_MAPPING.md §4-D7/D8·Q2），这里用
 * 「项目选择器 + 仅我的」诚实表达：project_id 来自下拉，assignee_id=当前用户
 * 表达「我的任务」。顶部 el-alert 明示该约束，不编造全局端点。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { taskApi } from '@/api/task'
import { projectApi } from '@/api/project'
import { teamApi } from '@/api/team'
import { useAuthStore } from '@/stores/auth'
import EmptyState from '@/components/common/EmptyState.vue'
import { FolderOpened, Search, Tickets } from '@element-plus/icons-vue'
import {
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_STATUS_ORDER,
  TASK_PRIORITY_ORDER,
  type Task,
  type TaskStatus,
  type TaskPriority,
  type TaskListParams,
  type TaskSortField,
  type TaskSortOrder,
} from '@/types/task'
import type { Project } from '@/types/project'
import type { TeamMember } from '@/types/team'

const router = useRouter()
const authStore = useAuthStore()

/**
 * 可选 props（TASK-087）：
 * - `initialProjectId`：嵌入场景（项目详情 Tab）预选的项目；不存在于
 *   可见列表时回落第一个项目。缺省行为与原版一致（选第一个）。
 * - `embedded`：隐藏页内大标题，避免与外层 Tab 标签重复。
 */
const props = defineProps<{ initialProjectId?: number; embedded?: boolean }>()

const projects = ref<Project[]>([])
const members = ref<TeamMember[]>([])
const tasks = ref<Task[]>([])
const loading = ref(false)

const selectedProjectId = ref<number | null>(null)
const onlyMine = ref(false)
const filters = reactive<{
  keyword: string
  status: TaskStatus | ''
  priority: TaskPriority | ''
  assigneeId: number | null
}>({ keyword: '', status: '', priority: '', assigneeId: null })

const sort = ref<TaskSortField>('created_at')
const order = ref<TaskSortOrder>('desc')
const skip = ref(0)
const pageSize = 20

function statusTagType(status: TaskStatus): 'info' | 'warning' | 'primary' | 'success' | 'danger' {
  switch (status) {
    case 'TODO':
      return 'info'
    case 'IN_PROGRESS':
      return 'primary'
    case 'REVIEW':
      return 'warning'
    case 'DONE':
      return 'success'
    case 'CANCELLED':
      return 'danger'
  }
}

function priorityTagType(priority: TaskPriority): 'info' | 'success' | 'warning' | 'danger' {
  switch (priority) {
    case 'LOW':
      return 'info'
    case 'MEDIUM':
      return 'success'
    case 'HIGH':
      return 'warning'
    case 'URGENT':
      return 'danger'
  }
}

function assigneeText(task: Task): string {
  return task.assignees.length ? task.assignees.map((a) => a.username).join('、') : '—'
}

onMounted(loadProjects)

async function loadProjects(): Promise<void> {
  try {
    projects.value = await projectApi.listProjects()
    if (projects.value.length) {
      const wanted = props.initialProjectId
      selectedProjectId.value =
        wanted != null && projects.value.some((p) => p.id === wanted)
          ? wanted
          : projects.value[0].id
      await onProjectChange()
    }
  } catch {
    /* 错误提示由请求层统一给出 */
  }
}

async function onProjectChange(): Promise<void> {
  skip.value = 0
  members.value = []
  const proj = projects.value.find((p) => p.id === selectedProjectId.value)
  if (proj) {
    try {
      members.value = await teamApi.listMembers(proj.team_id)
    } catch {
      /* 非成员等情况由请求层提示 */
    }
  }
  await loadTasks()
}

async function loadTasks(): Promise<void> {
  if (!selectedProjectId.value) {
    tasks.value = []
    return
  }
  loading.value = true
  try {
    const params: TaskListParams = {
      project_id: selectedProjectId.value,
      skip: skip.value,
      limit: pageSize,
      sort: sort.value,
      order: order.value,
    }
    if (filters.keyword.trim()) params.keyword = filters.keyword.trim()
    if (filters.status) params.status = filters.status
    if (filters.priority) params.priority = filters.priority
    const assigneeId = onlyMine.value && authStore.currentUser ? authStore.currentUser.id : filters.assigneeId
    if (assigneeId) params.assignee_id = assigneeId
    tasks.value = await taskApi.listTasks(params)
  } catch {
    /* 错误提示由请求层统一给出 */
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  skip.value = 0
  void loadTasks()
}

function changeSort(): void {
  skip.value = 0
  void loadTasks()
}

function prevPage(): void {
  if (skip.value >= pageSize) {
    skip.value -= pageSize
    void loadTasks()
  }
}

function nextPage(): void {
  if (tasks.value.length === pageSize) {
    skip.value += pageSize
    void loadTasks()
  }
}

function goDetail(task: Task): void {
  router.push({ name: 'task-detail', params: { taskId: String(task.id) } })
}

function goCreate(): void {
  router.push({ name: 'task-create' })
}

/** 是否处于「筛选/仅我的」状态——空态据此区分「没有数据」与「被筛掉了」。 */
const hasFilter = computed(
  () =>
    filters.keyword.trim() !== '' ||
    filters.status !== '' ||
    filters.priority !== '' ||
    filters.assigneeId !== null ||
    onlyMine.value,
)

function clearFilters(): void {
  filters.keyword = ''
  filters.status = ''
  filters.priority = ''
  filters.assigneeId = null
  onlyMine.value = false
  applyFilters()
}

const emptyIcon = computed(() => {
  if (hasFilter.value) return Search
  return projects.value.length === 0 ? FolderOpened : Tickets
})

const emptyTitle = computed(() => {
  if (hasFilter.value) return '没有匹配的任务'
  if (projects.value.length === 0) return '你还没有项目'
  return '这个项目还没有任务'
})

const emptyDesc = computed(() => {
  if (hasFilter.value) {
    return '当前搜索/状态/优先级/负责人条件下没有结果——任务可能还在，只是被筛掉了。'
  }
  if (projects.value.length === 0) {
    return '任务是建立在项目之上的。先创建一个项目，再回到这里拆任务。'
  }
  return '拆出第一个任务、指定负责人与截止时间，它就会出现在项目看板和「我的待办」里。'
})
</script>

<template>
  <div class="task-list">
    <div class="page-header">
      <h2 v-if="!embedded" class="page-title">我的任务</h2>
      <el-button type="primary" @click="goCreate">新建任务</el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="按项目查看任务"
      description="后端 GET /tasks 要求 project_id 必填，没有跨项目的全局任务视图（见 docs/FRONTEND_API_MAPPING.md §4-D7/D8·Q2）。请先选择项目；勾选「仅我的」可按当前用户筛选负责任务。"
      class="scope-alert"
    />

    <div class="toolbar">
      <el-select
        v-model="selectedProjectId"
        placeholder="选择项目"
        class="project-select"
        :loading="loading"
        @change="onProjectChange"
      >
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-input
        v-model="filters.keyword"
        placeholder="搜索任务标题"
        clearable
        class="keyword-input"
        @keyup.enter="applyFilters"
        @clear="applyFilters"
      />
      <el-select v-model="filters.status" placeholder="状态" clearable class="filter-select" @change="applyFilters">
        <el-option v-for="s in TASK_STATUS_ORDER" :key="s" :label="TASK_STATUS_LABELS[s]" :value="s" />
      </el-select>
      <el-select v-model="filters.priority" placeholder="优先级" clearable class="filter-select" @change="applyFilters">
        <el-option v-for="p in TASK_PRIORITY_ORDER" :key="p" :label="TASK_PRIORITY_LABELS[p]" :value="p" />
      </el-select>
      <el-select
        v-model="filters.assigneeId"
        placeholder="负责人"
        clearable
        class="filter-select"
        :disabled="onlyMine"
        @change="applyFilters"
      >
        <el-option v-for="m in members" :key="m.user_id" :label="m.username" :value="m.user_id" />
      </el-select>
      <el-checkbox v-model="onlyMine" @change="applyFilters">仅我的</el-checkbox>
      <el-button @click="applyFilters">搜索</el-button>
    </div>

    <div class="toolbar toolbar-second">
      <span class="sort-label">排序：</span>
      <el-select v-model="sort" class="sort-select" @change="changeSort">
        <el-option label="创建时间" value="created_at" />
        <el-option label="截止时间" value="due_at" />
        <el-option label="优先级" value="priority" />
        <el-option label="ID" value="id" />
      </el-select>
      <el-select v-model="order" class="sort-select" @change="changeSort">
        <el-option label="降序" value="desc" />
        <el-option label="升序" value="asc" />
      </el-select>
    </div>

    <el-table v-loading="loading" :data="tasks" row-key="id" class="task-table" @row-click="goDetail">
      <!-- 空态三分流（TASK-130）：还没选项目 / 项目里确实没任务 / 筛选后没结果。
           旧版只有一句「该项目暂无任务」，在没有项目可选时还会显示它——用户会
           以为是这个项目没任务，而真正的问题是「你还没有项目」。 -->
      <template #empty>
        <EmptyState
          :icon="emptyIcon"
          :title="emptyTitle"
          :description="emptyDesc"
          size="sm"
        >
          <template #actions>
            <el-button v-if="hasFilter" @click="clearFilters">清除筛选</el-button>
            <el-button v-else-if="projects.length === 0" type="primary" @click="router.push('/projects')">
              先去建项目
            </el-button>
            <el-button v-else type="primary" @click="goCreate">新建任务</el-button>
          </template>
        </EmptyState>
      </template>
      <el-table-column prop="title" label="任务名称" min-width="200">
        <template #default="{ row }">
          <span class="task-title">{{ row.title }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="priority" label="优先级" width="100">
        <template #default="{ row }">
          <el-tag :type="priorityTagType(row.priority)" size="small">{{ TASK_PRIORITY_LABELS[row.priority as TaskPriority] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ TASK_STATUS_LABELS[row.status as TaskStatus] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="负责人" min-width="140">
        <template #default="{ row }">
          {{ assigneeText(row as Task) }}
        </template>
      </el-table-column>
      <el-table-column prop="due_at" label="截止时间" min-width="170">
        <template #default="{ row }">
          {{ row.due_at ? new Date(row.due_at).toLocaleString() : '—' }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pager">
      <el-button :disabled="skip <= 0" @click="prevPage">上一页</el-button>
      <span class="pager-info">第 {{ Math.floor(skip / pageSize) + 1 }} 页</span>
      <el-button :disabled="tasks.length < pageSize" @click="nextPage">下一页</el-button>
    </div>
  </div>
</template>

<style scoped>
.task-list {
  padding: 16px;
}
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.scope-alert {
  margin-bottom: 16px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}
.project-select {
  width: 180px;
}
.keyword-input {
  width: 200px;
}
.filter-select {
  width: 120px;
}
.sort-select {
  width: 130px;
}
.sort-label {
  color: var(--el-text-color-secondary);
}
.task-table {
  margin-bottom: 12px;
  cursor: pointer;
}
.task-title {
  font-weight: 500;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.pager-info {
  color: var(--el-text-color-secondary);
}
</style>
