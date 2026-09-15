<script setup lang="ts">
/**
 * 任务列表（前端规格 §20 / 阶段 8）。
 *
 * 后端 `GET /api/v1/tasks` 能力比规格假设的更全：支持 status / priority /
 * keyword / assignee_id / skip / limit / sort / order，**但 project_id 必填**。
 * 这是本页面最大的设计约束——它不是一个「全局我的任务」页面。
 */
import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="我的任务"
    phase="阶段 8（任务）"
    :api="['GET /api/v1/tasks?project_id=…&assignee_id=…&status=…&keyword=…&sort=…&order=…']"
    note="project_id 是必填参数，所以本页面需要先选定项目（或改为「按项目分别加载后合并」）；「我的任务」用 assignee_id=当前用户 表达，而不是一个独立端点。"
  />
</template>
