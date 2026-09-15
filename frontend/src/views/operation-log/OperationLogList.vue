<script setup lang="ts">
/**
 * 操作日志（前端规格 §32 / 阶段 13）。
 *
 * 两个端点的语义差别要记住：`GET /logs` 只返回**当前用户自己**的时间线
 * （资源级隔离）；`GET /logs/{resource_type}/{resource_id}` 返回某个资源的日志，
 * 由后端校验调用者对该资源的归属。
 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="操作日志"
    phase="阶段 13（日志）"
    :api="['GET /api/v1/logs?skip=0&limit=100', 'GET /api/v1/logs/{resource_type}/{resource_id}']"
    note="payload 是后端原样透传的 JSONB，字段随资源类型而变化，渲染时需要按 resource_type 决定展示方式。"
  />
</template>
