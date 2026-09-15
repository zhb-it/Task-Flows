<script setup lang="ts">
/** 项目详情（前端规格 §18 / 阶段 7）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

defineProps<{ projectId?: string }>()
</script>

<template>
  <PagePlaceholder
    :title="`项目详情（project_id = ${projectId}）`"
    phase="阶段 7（项目）"
    :api="['GET /api/v1/projects/{project_id}', 'GET /api/v1/tasks?project_id={project_id}']"
    note="这是任务列表的天然入口：GET /api/v1/tasks 必须带 project_id，所以「我的任务」只能落在项目上下文里（见路由表的说明）。"
  />
</template>
