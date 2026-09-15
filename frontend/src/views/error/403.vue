<script setup lang="ts">
/**
 * 403 页面（前端规格 §72）。
 *
 * 规格 §35 的原则在这里有个直接推论：**前端的 403 只是提示，不是防线**。
 * 真正决定「能不能访问」的是后端——它在每个端点上都用 `require_permission`
 * / 资源归属校验裁决。因此这个页面只在后端明确返回 403 时展示（例如账号被禁用、
 * 缺少功能级权限），不靠前端自己判断「有没有权限」然后跳转。
 */

import { useRouter } from 'vue-router'

const router = useRouter()

function goHome(): void {
  void router.replace({ name: 'dashboard' })
}

function goBack(): void {
  router.back()
}
</script>

<template>
  <div class="tf-error">
    <el-result icon="warning" title="403" sub-title="没有权限访问该页面">
      <template #extra>
        <el-button type="primary" @click="goHome">返回首页</el-button>
        <el-button @click="goBack">返回上一页</el-button>
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
