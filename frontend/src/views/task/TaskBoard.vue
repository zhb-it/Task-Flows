<script setup lang="ts">
/** 任务看板（前端规格 §23 / 阶段 8）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="任务看板"
    phase="阶段 8（任务）"
    :api="['GET /api/v1/tasks?project_id=…&status=…', 'POST /api/v1/tasks/{task_id}/transition']"
    note="看板按状态分列，列内数据用带 status 的同一列表接口；拖拽换列必须调用 transition 端点（状态机有合法转移约束），不能直接 PATCH status 字段。"
  />
</template>
