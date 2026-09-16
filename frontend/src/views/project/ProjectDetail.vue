<script setup lang="ts">
/** 项目详情（前端规格 §18 / 阶段 7）。 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { teamApi } from '@/api/team'
import { projectApi } from '@/api/project'
import type { Project } from '@/types/project'
import type { TeamMember } from '@/types/team'
import { formatDateTime } from '@/utils/format'
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.projectId)

const loading = ref(false)
const project = ref<Project | null>(null)
const members = ref<TeamMember[]>([])
const membersLoading = ref(false)
const activeTab = ref('tasks')

const teamName = computed(() => {
  if (!project.value) return ''
  return `团队 #${project.value.team_id}`
})

async function loadProject(): Promise<void> {
  loading.value = true
  try {
    project.value = await projectApi.getProject(projectId)
  } catch {
    // 404 非团队成员由请求层提示。
  } finally {
    loading.value = false
  }
}

async function loadMembers(): Promise<void> {
  if (!project.value) return
  membersLoading.value = true
  try {
    // 项目成员关系挂在团队上，复用团队成员接口（项目没有独立成员端点）。
    members.value = await teamApi.listMembers(project.value.team_id)
  } catch {
    // 请求层已提示。
  } finally {
    membersLoading.value = false
  }
}

function onTabChange(tab: string | number): void {
  if (String(tab) === 'members') void loadMembers()
}

function goSettings(): void {
  router.push({ name: 'project-settings', params: { projectId: String(projectId) } })
}

function back(): void {
  router.push({ name: 'project-list' })
}

onMounted(loadProject)
</script>

<template>
  <div class="project-detail">
    <div class="page-header">
      <div>
        <el-button link @click="back">← 返回项目列表</el-button>
        <h2 class="page-title">{{ project?.name ?? '项目详情' }}</h2>
        <p class="page-sub">{{ project?.description || '暂无描述' }}</p>
        <p v-if="project" class="page-meta">
          所属：<el-tag size="small" effect="plain">{{ teamName }}</el-tag>
          <span class="muted"> · 创建于 {{ formatDateTime(project.created_at) }}</span>
        </p>
      </div>
      <el-button type="primary" @click="goSettings">项目设置</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="任务列表" name="tasks">
        <PagePlaceholder
          title="任务列表"
          phase="阶段 8（任务模块，待实现）"
          :api="['GET /api/v1/tasks?project_id=必填']"
          note="后端 GET /tasks 把 project_id 列为必填查询参数，任务列表必须在「项目上下文」内工作。任务模块将在阶段 8 实现，这里先占位。"
        />
      </el-tab-pane>
      <el-tab-pane label="任务看板" name="board">
        <PagePlaceholder
          title="任务看板"
          phase="阶段 8（任务模块，待实现）"
          :api="['GET /api/v1/tasks?project_id=必填']"
          note="看板形态（按状态分列）依赖任务列表数据，随阶段 8 一并实现。"
        />
      </el-tab-pane>
      <el-tab-pane label="项目成员" name="members">
        <div v-loading="membersLoading">
          <el-table v-if="members.length" :data="members" stripe empty-text="该团队暂无成员">
            <el-table-column prop="username" label="用户名" min-width="160" />
            <el-table-column prop="role" label="角色" width="120">
              <template #default="{ row }">
                <el-tag
                  :type="row.role === 'owner' ? 'danger' : row.role === 'admin' ? 'warning' : 'info'"
                  size="small"
                >
                  {{ row.role }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="joined_at" label="加入时间" min-width="170">
              <template #default="{ row }">{{ formatDateTime(row.joined_at) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-else description="暂无成员数据" />
        </div>
      </el-tab-pane>
      <el-tab-pane label="项目设置" name="settings">
        <el-alert
          type="info"
          :closable="false"
          show-icon
          title="项目设置"
          description="可在此修改项目名称 / 描述，或删除项目（仅团队 Owner / Admin 有权限，由后端校验）。"
        />
        <div style="margin-top: 16px">
          <el-button type="primary" @click="goSettings">打开项目设置</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.project-detail {
  padding: 4px;
}
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}
.page-title {
  margin: 4px 0;
  font-size: 20px;
  font-weight: 600;
}
.page-sub {
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.page-meta {
  margin: 6px 0 0;
  font-size: 13px;
}
.muted {
  color: var(--el-text-color-secondary);
}
</style>
