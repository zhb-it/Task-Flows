<script setup lang="ts">
/**
 * 任务看板（前端规格 §23 / 阶段 8）。
 *
 * 按状态分列（5 态，含 CANCELLED；规格 §23 图示列 4 列为其子集，但后端数据为 5 态）。
 * 列内数据来自同一列表接口（不带 status 过滤、一次拉全项目的任务），前端按
 * status 分组渲染。
 *
 * 拖拽换列必须调用 `POST /tasks/{id}/transition`（状态机有合法转移约束，普通
 * PATCH status 会被后端拒绝，决策 005 / TASK-038）。前端用 `TASK_TRANSITIONS`
 * 仅做「可拖入列」的白名单提示（规格 §24：前端只显示合法操作），最终仍以后端
 * 为准——后端还会叠加 `task:transition` 功能级权限（普通成员无此权限 → 403，
 * 见 docs/FRONTEND_API_MAPPING.md §4-D11）。拖拽非法目标不调接口；拖拽合法目标
 * 调接口，成功才移动卡片，失败（403/409）保留原位、提示由请求层给出。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { taskApi } from '@/api/task'
import { projectApi } from '@/api/project'
import {
  TASK_STATUS_LABELS,
  TASK_STATUS_ORDER,
  TASK_TRANSITIONS,
  type Task,
  type TaskStatus,
} from '@/types/task'
import type { Project } from '@/types/project'

const projects = ref<Project[]>([])
const tasks = ref<Task[]>([])
const loading = ref(false)
const selectedProjectId = ref<number | null>(null)
// 拖拽中任务的状态：dragover 阶段浏览器禁止读取 dataTransfer 数据，
// 故用 ref 记录当前拖拽任务的状态用于「可拖入列」判定（drop 时再读 id）。
const draggingId = ref<number | null>(null)
const draggingStatus = ref<TaskStatus | null>(null)

const grouped = computed<Record<TaskStatus, Task[]>>(() => {
  const map = {} as Record<TaskStatus, Task[]>
  for (const s of TASK_STATUS_ORDER) map[s] = []
  for (const t of tasks.value) map[t.status].push(t)
  return map
})

onMounted(loadProjects)

async function loadProjects(): Promise<void> {
  try {
    projects.value = await projectApi.listProjects()
    if (projects.value.length) {
      selectedProjectId.value = projects.value[0].id
      await onProjectChange()
    }
  } catch {
    /* 请求层提示 */
  }
}

async function onProjectChange(): Promise<void> {
  await loadBoard()
}

async function loadBoard(): Promise<void> {
  if (!selectedProjectId.value) {
    tasks.value = []
    return
  }
  loading.value = true
  try {
    // 一次拉全项目任务（不带 status 过滤），前端分组渲染看板。
    tasks.value = await taskApi.listTasks({
      project_id: selectedProjectId.value,
      skip: 0,
      limit: 100,
      sort: 'priority',
      order: 'desc',
    })
  } catch {
    /* 请求层提示 */
  } finally {
    loading.value = false
  }
}

function canDrop(current: TaskStatus, target: TaskStatus): boolean {
  return current !== target && TASK_TRANSITIONS[current].includes(target)
}

function onDragStart(event: DragEvent, task: Task): void {
  draggingId.value = task.id
  draggingStatus.value = task.status
  event.dataTransfer?.setData('text/plain', String(task.id))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(event: DragEvent, target: TaskStatus): void {
  // dragover 阶段无法读取 dataTransfer，用 draggingStatus 判定是否允许落入。
  if (draggingStatus.value && canDrop(draggingStatus.value, target)) {
    event.preventDefault()
  }
}

async function onDrop(event: DragEvent, target: TaskStatus): Promise<void> {
  const id = Number(event.dataTransfer?.getData('text/plain'))
  draggingId.value = null
  draggingStatus.value = null
  const task = tasks.value.find((t) => t.id === id)
  if (!task) return
  if (!canDrop(task.status, target)) {
    if (task.status !== target) ElMessage.warning('非法状态流转')
    return
  }
  try {
    const updated = await taskApi.transitionTask(task.id, target)
    // 成功才更新本地卡片状态（重新分组），保持与后端一致。
    const idx = tasks.value.findIndex((t) => t.id === task.id)
    if (idx >= 0) tasks.value[idx] = updated
  } catch {
    // 403（无 task:transition 权限）/ 409（状态机拒绝）由请求层统一提示，原位保留。
  }
}
</script>

<template>
  <div class="task-board">
    <div class="page-header">
      <h2 class="page-title">任务看板</h2>
      <el-select
        v-model="selectedProjectId"
        placeholder="选择项目"
        class="project-select"
        :loading="loading"
        @change="onProjectChange"
      >
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="看板按状态分列，拖拽换列即流转状态"
      description="拖拽合法目标列会调用状态机端点；普通成员可能没有 task:transition 权限（删除/流转受后端功能级权限控制，见 §4-D11），此时拖拽会被后端 403 拒绝。"
      class="scope-alert"
    />

    <div v-loading="loading" class="board">
      <div
        v-for="status in TASK_STATUS_ORDER"
        :key="status"
        class="board-column"
        :class="{ 'drop-allowed': draggingId !== null && draggingStatus && canDrop(draggingStatus, status) }"
        @dragover="onDragOver($event, status)"
        @drop="onDrop($event, status)"
      >
        <div class="column-header">
          <span class="column-title">{{ TASK_STATUS_LABELS[status] }}</span>
          <el-tag size="small" type="info">{{ grouped[status].length }}</el-tag>
        </div>
        <div class="column-body">
          <div
            v-for="task in grouped[status]"
            :key="task.id"
            class="task-card"
            draggable="true"
            @dragstart="onDragStart($event, task)"
          >
            <div class="card-title">{{ task.title }}</div>
            <div class="card-meta">
              <el-tag size="small" :type="task.priority === 'URGENT' ? 'danger' : task.priority === 'HIGH' ? 'warning' : task.priority === 'MEDIUM' ? 'success' : 'info'">
                {{ task.priority }}
              </el-tag>
              <span v-if="task.assignees.length" class="card-assignee">{{ task.assignees[0].username }}</span>
            </div>
          </div>
          <div v-if="!grouped[status].length" class="column-empty">暂无任务</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-board {
  padding: 16px;
  height: 100%;
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
.project-select {
  width: 200px;
}
.scope-alert {
  margin-bottom: 16px;
}
.board {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  overflow-x: auto;
}
.board-column {
  flex: 0 0 240px;
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 8px;
  min-height: 200px;
  border: 1px dashed transparent;
}
.board-column.drop-allowed {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-weight: 600;
}
.column-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 60px;
}
.task-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px;
  cursor: grab;
}
.task-card:active {
  cursor: grabbing;
}
.card-title {
  font-weight: 500;
  margin-bottom: 6px;
}
.card-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.card-assignee {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.column-empty {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  text-align: center;
  padding: 12px 0;
}
</style>
