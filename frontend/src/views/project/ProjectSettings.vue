<script setup lang="ts">
/** 项目设置（前端规格 §4 目录 / 阶段 7）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

defineProps<{ projectId?: string }>()
</script>

<template>
  <PagePlaceholder
    :title="`项目设置（project_id = ${projectId}）`"
    phase="阶段 7（项目）"
    :api="['PATCH /api/v1/projects/{project_id}', 'DELETE /api/v1/projects/{project_id}']"
    note="删除是不可逆的危险操作，按规格 §44 必须二次确认；同时后端把「非 OWNER/ADMIN」表达成 404，而不是 403。"
  />
</template>
