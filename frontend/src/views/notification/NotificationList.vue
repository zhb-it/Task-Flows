<script setup lang="ts">
/**
 * 通知列表（前端规格 §30 / 阶段 11）。
 *
 * 后端 `GET /api/v1/notifications` 只支持 skip/limit，没有「仅看未读」参数，
 * 也没有未读数端点；列表已是时间倒序，直接用即可。
 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="通知"
    phase="阶段 11（通知）"
    :api="[
      'GET /api/v1/notifications?skip=0&limit=100',
      'PATCH /api/v1/notifications/read-all',
      'PATCH /api/v1/notifications/{notification_id}/read',
    ]"
    note="「未读筛选」「未读总数」需要前端在取回的列表上自己统计；分页只有 skip/limit，响应里没有总数，因此分页器只能做「上一页 / 下一页」。"
  />
</template>
