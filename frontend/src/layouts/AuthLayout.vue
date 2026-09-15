<script setup lang="ts">
/**
 * 认证页布局（前端规格 §61 第二阶段 / §7 登录页 / §8 注册页）。
 *
 * 只有一个居中的卡片。规格 §7 的示意图里没有侧边栏和顶栏，所以登录/注册
 * 不使用 `BasicLayout`——两套布局分别挂在 `/login`、`/register` 与其余路由上
 * （见 `router/routes.ts`）。
 *
 * 站点名从环境变量取（`VITE_APP_TITLE`），而不是写死在模板里：生产与开发
 * 使用同一份代码，标题属于部署配置。
 */

import { APP_TITLE } from '@/router/routes'
</script>

<template>
  <div class="tf-auth">
    <el-card class="tf-auth__card" shadow="always">
      <div class="tf-auth__brand">
        <span class="tf-auth__logo">TF</span>
        <h1 class="tf-auth__title">{{ APP_TITLE }}</h1>
      </div>
      <router-view />
    </el-card>
    <p class="tf-auth__footer">团队任务协作系统 · 前端</p>
  </div>
</template>

<style scoped>
.tf-auth {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: 24px;
  background: linear-gradient(160deg, #f0f5ff 0%, #f5f7fa 60%, #eef2f7 100%);
}

.tf-auth__card {
  width: 100%;
  max-width: 400px;
}

.tf-auth__brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  margin-bottom: 20px;
}

.tf-auth__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  background-color: #409eff;
  color: #ffffff;
  font-weight: 700;
  font-size: 14px;
}

.tf-auth__title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.tf-auth__footer {
  margin: 16px 0 0;
  color: #909399;
  font-size: 12px;
}
</style>
