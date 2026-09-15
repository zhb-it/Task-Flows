<script setup lang="ts">
/**
 * 首页 Dashboard（前端规格 §11 / 阶段 4）。
 *
 * 占位说明里要特别提一句「任务统计」：规格 §11.2 要求展示任务统计，但后端
 * `GET /api/v1/tasks` 把 `project_id` 声明为**必填**（`app/api/v1/tasks.py`），
 * 没有「跨项目的任务概览」端点。所以这一块在实现阶段需要先决定方案：
 * 逐项目拉取后合并统计，或者由后端补一个统计端点。
 */

import PagePlaceholder from '@/components/common/PagePlaceholder.vue'
</script>

<template>
  <PagePlaceholder
    title="首页"
    phase="阶段 4（Dashboard）"
    :api="[
      'GET /api/v1/teams',
      'GET /api/v1/projects',
      'GET /api/v1/notifications',
      'GET /api/v1/logs',
    ]"
    note="规格 §11.2 的「任务统计」缺少跨项目接口：GET /api/v1/tasks 要求 project_id 必填，需先确定按项目汇总还是新增后端统计端点。"
  />
</template>
