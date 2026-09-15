<script setup lang="ts">
/** 团队详情（前端规格 §13 / 阶段 6）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

defineProps<{ teamId?: string }>()
</script>

<template>
  <PagePlaceholder
    :title="`团队详情（team_id = ${teamId}）`"
    phase="阶段 6（团队）"
    :api="['GET /api/v1/teams/{team_id}', 'PATCH /api/v1/teams/{team_id}']"
    note="改名的资源级权限由后端裁决：非 OWNER/ADMIN 时返回 404（与「不存在」同文案，防 id 枚举），页面按 404 处理即可。"
  />
</template>
