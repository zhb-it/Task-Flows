<script setup lang="ts">
/**
 * 应用根组件。
 *
 * 只做一件事：交出路由出口。全局的布局选择由路由表决定
 * （`AuthLayout` 还是 `BasicLayout`，见 `router/routes.ts`），根组件不参与判断。
 */
</script>

<template>
  <router-view />
</template>
