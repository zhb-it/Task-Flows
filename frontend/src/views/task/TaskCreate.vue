<script setup lang="ts">
/**
 * 新建任务（前端规格 §26 / 阶段 8）。
 *
 * 字段对齐 `app/schemas/task.py::TaskCreate`：project_id / title / description /
 * priority / due_at（**不含 status**——新任务恒为 TODO；**不含 assignee**——负责人
 * 通过创建后的 `POST /tasks/{id}/assignees` 添加，见 DECISIONS / FRONTEND_API_MAPPING）。
 * 表单可选地选「负责人」，提交成功后若已选则追加一次指派调用，与后端契约一致。
 *
 * 负责人下拉的数据来自「所选项目所属团队的成员」（ProjectRead.team_id →
 * GET /teams/{team_id}/members）。
 */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { taskApi } from '@/api/task'
import { projectApi } from '@/api/project'
import { teamApi } from '@/api/team'
import {
  TASK_PRIORITY_LABELS,
  type TaskPriority,
  type TaskCreate,
} from '@/types/task'
import type { Project } from '@/types/project'
import type { TeamMember } from '@/types/team'

const router = useRouter()

const projects = ref<Project[]>([])
const members = ref<TeamMember[]>([])
const submitting = ref(false)

const form = reactive<TaskCreate & { assigneeId: number | null }>({
  project_id: 0,
  title: '',
  description: '',
  priority: 'MEDIUM',
  due_at: null,
  assigneeId: null,
})

const priorityOptions: TaskPriority[] = ['LOW', 'MEDIUM', 'HIGH', 'URGENT']

async function loadProjects(): Promise<void> {
  try {
    projects.value = await projectApi.listProjects()
    if (projects.value.length && !form.project_id) {
      form.project_id = projects.value[0].id
      await onProjectChange()
    }
  } catch {
    /* 请求层提示 */
  }
}

async function onProjectChange(): Promise<void> {
  members.value = []
  form.assigneeId = null
  const proj = projects.value.find((p) => p.id === form.project_id)
  if (proj) {
    try {
      members.value = await teamApi.listMembers(proj.team_id)
    } catch {
      /* 请求层提示 */
    }
  }
}

async function submit(): Promise<void> {
  if (!form.title.trim()) {
    ElMessage.warning('请填写任务标题')
    return
  }
  if (!form.project_id) {
    ElMessage.warning('请选择项目')
    return
  }
  submitting.value = true
  try {
    const payload: TaskCreate = {
      project_id: form.project_id,
      title: form.title.trim(),
      description: form.description || null,
      priority: form.priority,
      due_at: form.due_at || null,
    }
    const created = await taskApi.createTask(payload)
    if (form.assigneeId != null) {
      try {
        await taskApi.assignTask(created.id, form.assigneeId)
      } catch {
        // 指派失败不影响任务已创建；提示由请求层给出，任务详情页可再次指派。
      }
    }
    ElMessage.success('任务已创建')
    router.push({ name: 'task-detail', params: { taskId: String(created.id) } })
  } catch {
    /* 请求层提示 */
  } finally {
    submitting.value = false
  }
}

void loadProjects()
</script>

<template>
  <div class="task-create">
    <div class="page-header">
      <h2 class="page-title">新建任务</h2>
    </div>

    <el-card shadow="never" class="form-card">
      <el-form :model="form" label-width="90px" class="create-form">
        <el-form-item label="项目" required>
          <el-select v-model="form.project_id" placeholder="选择项目" class="full" @change="onProjectChange">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="请输入任务标题" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="可选" />
        </el-form-item>
        <el-form-item label="优先级" required>
          <el-select v-model="form.priority" class="full">
            <el-option v-for="p in priorityOptions" :key="p" :label="TASK_PRIORITY_LABELS[p]" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker
            v-model="form.due_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            placeholder="选择截止时间（可选）"
            class="full"
          />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="form.assigneeId" placeholder="可选，创建后也可在详情添加" class="full" clearable :disabled="!form.project_id">
            <el-option v-for="m in members" :key="m.user_id" :label="m.username" :value="m.user_id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">创建任务</el-button>
          <el-button @click="router.push({ name: 'task-list' })">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.task-create {
  padding: 16px;
}
.page-header {
  margin-bottom: 12px;
}
.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.form-card {
  max-width: 640px;
}
.full {
  width: 100%;
}
</style>
