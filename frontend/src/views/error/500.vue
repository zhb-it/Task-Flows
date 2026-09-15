<script setup lang="ts">
/**
 * 500 页面（前端规格 §72）。
 *
 * 后端把「预期内的业务错误」都表达成了带语义的状态码（400/401/403/404/409/
 * 422/429，见 `app/core/exceptions.py`），500 只剩「未预期的服务端异常」。
 * 这类错误通常伴随 request_id（后端每个请求都会生成并记日志），所以页面上提示
 * 用户「让运维查日志」是有依据的——后端日志里能靠 request_id 定位到那一次请求。
 */

import { useRouter } from 'vue-router'

const router = useRouter()

function goHome(): void {
  void router.replace({ name: 'dashboard' })
}
</script>

<template>
  <div class="tf-error">
    <el-result
      icon="error"
      title="500"
      sub-title="服务器异常，请稍后重试；若持续出现请联系管理员并提供发生时间"
    >
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
