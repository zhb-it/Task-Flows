<script setup lang="ts">
/** 团队成员管理（前端规格 §14 / §15 团队邀请 / 阶段 6）。 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'

defineProps<{ teamId?: string }>()
</script>

<template>
  <PagePlaceholder
    :title="`成员管理（team_id = ${teamId}）`"
    phase="阶段 6（团队）"
    :api="[
      'GET /api/v1/teams/{team_id}/members',
      'POST /api/v1/teams/{team_id}/members',
      'DELETE /api/v1/teams/{team_id}/members/{user_id}',
    ]"
    note="邀请是按 user_id 添加（不是邮箱邀请），role 只接受 admin / member；owner 只能通过创建团队或转让获得，传 owner 会 422。"
  />
</template>
