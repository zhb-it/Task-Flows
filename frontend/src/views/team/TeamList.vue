<script setup lang="ts">
/** 团队列表（前端规格 §12 / 阶段 6）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="团队"
    phase="阶段 6（团队）"
    :api="['POST /api/v1/teams', 'GET /api/v1/teams', 'DELETE /api/v1/teams/{team_id}']"
    note="GET /api/v1/teams 没有分页与搜索参数，返回的是当前用户可见的团队全量列表；仅返回 list，无总数。"
  />
</template>
