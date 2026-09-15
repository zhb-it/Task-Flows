<script setup lang="ts">
/**
 * 任务详情（前端规格 §25 / §24 状态流转 / §28 评论 / §29 附件 / 阶段 8-10）。
 *
 * 状态流转必须走 `POST /tasks/{id}/transition` 而不是 PATCH 字段：后端有独立
 * 状态机（`app/services/state_machine.py`），非法转移会被拒绝。
 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

defineProps<{ taskId?: string }>()
</script>

<template>
  <PagePlaceholder
    :title="`任务详情（task_id = ${taskId}）`"
    phase="阶段 8（任务）"
    :api="[
      'GET /api/v1/tasks/{task_id}',
      'PATCH /api/v1/tasks/{task_id}',
      'POST /api/v1/tasks/{task_id}/transition',
      'POST /api/v1/tasks/{task_id}/assignees',
      'GET /api/v1/tasks/{task_id}/comments',
      'GET /api/v1/tasks/{task_id}/attachments',
      'GET /api/v1/logs/task/{task_id}',
    ]"
    note="评论、附件、操作日志都挂在这个页面下，因此它是跨阶段页面：主体在阶段 8，评论阶段 9，附件阶段 10，日志阶段 13。"
  />
</template>
