<script setup lang="ts">
/** 项目设置（前端规格 §17 / §19 / 阶段 7）。 */
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

import { projectApi } from '@/api/project'
import type { Project, ProjectUpdate } from '@/types/project'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.projectId)

const loading = ref(false)
const saving = ref(false)
const project = ref<Project | null>(null)
const formRef = ref<FormInstance>()
const form = reactive<ProjectUpdate>({ name: '', description: '' })
const rules: FormRules<ProjectUpdate> = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

async function load(): Promise<void> {
  loading.value = true
  try {
    project.value = await projectApi.getProject(projectId)
    form.name = project.value.name
    form.description = project.value.description ?? ''
  } catch {
    // 404 非团队成员由请求层提示。
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    saving.value = true
    try {
      await projectApi.updateProject(projectId, { ...form })
      ElMessage.success('项目已更新')
      router.push({ name: 'project-detail', params: { projectId: String(projectId) } })
    } catch {
      // 403 / 404（非 OWNER/ADMIN）由请求层提示。
    } finally {
      saving.value = false
    }
  })
}

async function remove(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定要删除项目「${project.value?.name ?? ''}」吗？该操作不可恢复，且会一并删除其下的任务。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  try {
    await projectApi.deleteProject(projectId)
    ElMessage.success('项目已删除')
    router.push({ name: 'project-list' })
  } catch {
    // 404 / 403 由请求层提示。
  }
}

function back(): void {
  router.push({ name: 'project-detail', params: { projectId: String(projectId) } })
}

onMounted(load)
</script>

<template>
  <div class="project-settings">
    <el-button link @click="back">← 返回项目</el-button>
    <h2 class="page-title">{{ project?.name ?? '项目设置' }}</h2>

    <el-card v-loading="loading" class="form-card">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px" style="max-width: 520px">
        <el-form-item label="所属团队">
          <el-tag v-if="project" size="small" effect="plain">团队 #{{ project.team_id }}</el-tag>
          <span class="muted">（团队不可变更）</span>
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" maxlength="150" placeholder="项目名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="4"
            maxlength="255"
            placeholder="选填"
          />
        </el-form-item>
        <el-form-item v-if="project" label="创建于">
          <span class="muted">{{ formatDateTime(project.created_at) }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          <el-button @click="back">取消</el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <div class="danger-zone">
        <div>
          <div class="dz-title">删除项目</div>
          <div class="muted">删除后项目及其任务将不可恢复。仅团队 Owner / Admin 可执行（后端校验）。</div>
        </div>
        <el-button type="danger" @click="remove">删除项目</el-button>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.project-settings {
  padding: 4px;
}
.page-title {
  margin: 4px 0 16px;
  font-size: 20px;
  font-weight: 600;
}
.form-card {
  margin-top: 12px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.danger-zone {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 16px;
  border: 1px solid var(--el-color-danger-light-5);
  border-radius: 6px;
  background: var(--el-color-danger-light-9);
}
.dz-title {
  font-weight: 600;
  margin-bottom: 4px;
}
</style>
