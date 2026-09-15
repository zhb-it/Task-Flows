<script setup lang="ts">
/**
 * 404 页面（前端规格 §72）。
 *
 * 由路由表的 catch-all（`/:pathMatch(.*)*`）兜底，覆盖两种情况：
 * 前端确实没有这条路由；或者用户手输了一个不存在的地址。
 *
 * 注意区分：后端返回的 404 有完全不同的含义——`ResourceNotFoundError` 同时
 * 表达「资源不存在」和「资源不在你的归属链上」（`app/core/exceptions.py`，
 * 防 id 枚举）。那是数据层面的 404，由具体页面处理，不该跳到这个页面。
 */

import { useRouter } from 'vue-router'

const router = useRouter()

function goHome(): void {
  void router.replace({ name: 'dashboard' })
}
</script>

<template>
  <div class="tf-error">
    <el-result icon="info" title="404" sub-title="页面不存在">
      <template #extra>
        <el-button type="primary" @click="goHome">返回首页</el-button>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.tf-error {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
}
</style>
