<script setup lang="ts">
/** 新建任务（前端规格 §26 / 阶段 8）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="新建任务"
    phase="阶段 8（任务）"
    :api="['POST /api/v1/tasks']"
    note="请求体字段以 app/schemas/task.py 的 TaskCreate 为准（规格 §57：不猜字段）；任务的负责人通过 POST /api/v1/tasks/{task_id}/assignees 单独添加。"
  />
</template>
