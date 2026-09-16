<script setup lang="ts">
/**
 * 任务详情（前端规格 §25 / §24 状态流转 / §27 编辑 / 阶段 8）。
 *
 * 主体在阶段 8：任务字段展示 + 状态流转 + 编辑 + 负责人管理 + 删除。
 * 评论（§28）、附件（阶段 10）、操作日志（阶段 13）挂在本页下，但属于后续阶段，
 * 此处以占位区块明示「尚未实现」，不编造接口（见 docs/FRONTEND_API_MAPPING.md §7）。
 *
 * 状态流转必须走 `POST /tasks/{id}/transition`（后端状态机）；普通成员可能无
 * `task:transition` 权限（§4-D11），点击后由后端 403 兜底。删除需团队 owner/admin，
 * 本页仅对「当前用户 == 项目 owner_id」显示删除钮（owner_id 是已知数据，可数据驱动
 * 隐藏；admin 角色未知，仍交给后端 403），其余操作按钮常显，越权由后端兜底。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { taskApi } from '@/api/task'
import { projectApi } from '@/api/project'
import { teamApi } from '@/api/team'
import { useAuthStore } from '@/stores/auth'
import {
  TASK_STATUS_LABELS,
  TASK_PRIORITY_LABELS,
  TASK_TRANSITIONS,
  type Task,
  type TaskStatus,
  type TaskPriority,
  type TaskUpdate,
} from '@/types/task'
import type { Project } from '@/types/project'
import type { TeamMember } from '@/types/team'

const props = defineProps<{ taskId?: string }>()
const router = useRouter()
const authStore = useAuthStore()

const task = ref<Task | null>(null)
const project = ref<Project | null>(null)
const members = ref<TeamMember[]>([])
const loading = ref(false)

const editVisible = ref(false)
const editForm = reactive<TaskUpdate>({})
const assigning = ref(false)
const assignUserId = ref<number | null>(null)
const saving = ref(false)

const taskIdNum = computed(() => Number(props.taskId))

const allowedTargets = computed<TaskStatus[]>(() =>
  task.value ? TASK_TRANSITIONS[task.value.status] : [],
)

const canDelete = computed(
  () => project.value != null && authStore.currentUser?.id === project.value.owner_id,
)

const creatorText = computed(() => {
  if (!task.value) return '—'
  const m = members.value.find((x) => x.user_id === task.value!.creator_id)
  return m ? m.username : `#${task.value.creator_id}`
})

onMounted(loadTask)

async function loadTask(): Promise<void> {
  loading.value = true
  try {
    const t = await taskApi.getTask(taskIdNum.value)
    task.value = t
    try {
      const proj = await projectApi.getProject(t.project_id)
      project.value = proj
      members.value = await teamApi.listMembers(proj.team_id)
    } catch {
      /* 项目/成员读取失败不阻断任务主体展示 */
    }
  } catch {
    /* 404 等由请求层提示 */
  } finally {
    loading.value = false
  }
}

async function doTransition(target: TaskStatus): Promise<void> {
  if (!task.value) return
  try {
    task.value = await taskApi.transitionTask(task.value.id, target)
    ElMessage.success('状态已更新')
  } catch {
    /* 403/409 由请求层提示，原位保留 */
  }
}

function openEdit(): void {
  if (!task.value) return
  editForm.title = task.value.title
  editForm.description = task.value.description
  editForm.priority = task.value.priority
  editForm.due_at = task.value.due_at
  editVisible.value = true
}

async function saveEdit(): Promise<void> {
  if (!task.value) return
  saving.value = true
  try {
    task.value = await taskApi.updateTask(task.value.id, { ...editForm })
    editVisible.value = false
    ElMessage.success('任务已更新')
  } catch {
    /* 请求层提示 */
  } finally {
    saving.value = false
  }
}

async function doAssign(): Promise<void> {
  if (!task.value || assignUserId.value == null) return
  assigning.value = true
  try {
    const a = await taskApi.assignTask(task.value.id, assignUserId.value)
    task.value.assignees = [...task.value.assignees, a]
    assignUserId.value = null
    ElMessage.success('已添加负责人')
  } catch {
    /* 404/409 由请求层提示 */
  } finally {
    assigning.value = false
  }
}

async function doUnassign(userId: number): Promise<void> {
  if (!task.value) return
  try {
    await taskApi.unassignTask(task.value.id, userId)
    task.value.assignees = task.value.assignees.filter((a) => a.user_id !== userId)
    ElMessage.success('已移除负责人')
  } catch {
    /* 请求层提示 */
  }
}

async function doDelete(): Promise<void> {
  if (!task.value) return
  try {
    await taskApi.deleteTask(task.value.id)
    ElMessage.success('任务已删除')
    router.push({ name: 'task-list' })
  } catch {
    /* 403 等由请求层提示 */
  }
}

const priorityOptions: TaskPriority[] = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']
function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString() : '—'
}
</script>

<template>
  <div v-loading="loading" class="task-detail">
    <template v-if="task">
      <div class="page-header">
        <div>
          <h2 class="page-title">{{ task.title }}</h2>
          <div class="sub">#{{ task.id }} · 项目 #{{ task.project_id }}</div>
        </div>
        <div class="header-actions">
          <el-button @click="router.push({ name: 'task-list' })">返回列表</el-button>
          <el-button type="primary" @click="openEdit">编辑</el-button>
          <el-popconfirm v-if="canDelete" title="确认删除该任务？" @confirm="doDelete">
            <template #reference>
              <el-button type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </div>
      </div>

      <el-alert
        v-if="allowedTargets.length === 0"
        type="warning"
        :closable="false"
        show-icon
        :title="task.status === 'DONE' ? '任务已完成（终态）' : '任务已取消（终态）'"
        description="终态任务无后续流转；如需重新开启请新建任务。"
        class="scope-alert"
      />

      <el-row :gutter="16">
        <el-col :span="16">
          <el-card class="block" shadow="never">
            <template #header>基本信息</template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="状态">
                <el-tag :type="task.status === 'DONE' ? 'success' : task.status === 'CANCELLED' ? 'danger' : task.status === 'REVIEW' ? 'warning' : task.status === 'IN_PROGRESS' ? 'primary' : 'info'">
                  {{ TASK_STATUS_LABELS[task.status] }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="优先级">
                <el-tag :type="task.priority === 'URGENT' ? 'danger' : task.priority === 'HIGH' ? 'warning' : task.priority === 'MEDIUM' ? 'success' : 'info'">
                  {{ TASK_PRIORITY_LABELS[task.priority] }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="创建人">{{ creatorText }}</el-descriptions-item>
              <el-descriptions-item label="截止时间">{{ fmt(task.due_at) }}</el-descriptions-item>
              <el-descriptions-item label="创建时间">{{ fmt(task.created_at) }}</el-descriptions-item>
              <el-descriptions-item label="更新时间">{{ fmt(task.updated_at) }}</el-descriptions-item>
              <el-descriptions-item label="描述" :span="2">{{ task.description || '—' }}</el-descriptions-item>
            </el-descriptions>

            <div v-if="allowedTargets.length" class="transition-bar">
              <span class="bar-label">流转状态：</span>
              <el-button
                v-for="t in allowedTargets"
                :key="t"
                size="small"
                @click="doTransition(t)"
              >
                转为「{{ TASK_STATUS_LABELS[t] }}」
              </el-button>
            </div>
          </el-card>

          <el-card class="block" shadow="never">
            <template #header>负责人</template>
            <div class="assignee-list">
              <el-tag v-for="a in task.assignees" :key="a.user_id" class="assignee-tag" closable @close="doUnassign(a.user_id)">
                {{ a.username }}
              </el-tag>
              <span v-if="!task.assignees.length" class="muted">暂无负责人</span>
            </div>
            <div class="assignee-add">
              <el-select v-model="assignUserId" placeholder="选择成员添加" class="assign-select" :disabled="assigning">
                <el-option v-for="m in members" :key="m.user_id" :label="m.username" :value="m.user_id" />
              </el-select>
              <el-button type="primary" :disabled="assignUserId == null" :loading="assigning" @click="doAssign">添加</el-button>
            </div>
          </el-card>

          <el-card class="block placeholder-block" shadow="never">
            <template #header>评论</template>
            <p class="muted">评论功能在阶段 9 实现（规格 §28），本区块为占位。</p>
          </el-card>
          <el-card class="block placeholder-block" shadow="never">
            <template #header>附件</template>
            <p class="muted">附件功能在阶段 10 实现，本区块为占位。</p>
          </el-card>
        </el-col>

        <el-col :span="8">
          <el-card class="block placeholder-block" shadow="never">
            <template #header>操作记录</template>
            <p class="muted">操作日志在阶段 13 实现（GET /logs/task/{id}），本区块为占位。</p>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" title="编辑任务" width="520px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="优先级">
          <el-select v-model="editForm.priority" class="full">
            <el-option v-for="p in priorityOptions" :key="p" :label="TASK_PRIORITY_LABELS[p]" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker
            v-model="editForm.due_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="选择截止时间"
            class="full"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.task-detail {
  padding: 16px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}
.page-title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.sub {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.scope-alert {
  margin-bottom: 16px;
}
.block {
  margin-bottom: 16px;
}
.transition-bar {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.bar-label {
  color: var(--el-text-color-secondary);
}
.assignee-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.assignee-add {
  display: flex;
  gap: 8px;
}
.assign-select {
  width: 200px;
}
.full {
  width: 100%;
}
.muted {
  color: var(--el-text-color-placeholder);
}
.placeholder-block {
  background: var(--el-fill-color-light);
}
</style>
