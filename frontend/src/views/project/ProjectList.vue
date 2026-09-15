<script setup lang="ts">
/** 项目列表（前端规格 §16.1 / 阶段 7）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="项目"
    phase="阶段 7（项目）"
    :api="['POST /api/v1/projects', 'GET /api/v1/projects']"
    note="GET /api/v1/projects 是纯列表（无分页、无搜索参数）。项目归属团队，因此新建项目前需要先有团队（team_id 必填）。"
  />
</template>
