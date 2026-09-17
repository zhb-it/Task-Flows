<script setup lang="ts">
/**
 * 应用根组件。
 *
 * 只做两件事：
 *
 * 1. 用 `<el-config-provider>` 提供中文 locale——Element Plus 按需引入后
 *    （TASK-080）入口不再 `app.use(ElementPlus, { locale })`，全局配置改由
 *    根组件下发，分页器、日期选择器、确认框等才有中文文案；
 * 2. 交出路由出口。全局的布局选择由路由表决定（`AuthLayout` 还是
 *    `BasicLayout`，见 `router/routes.ts`），根组件不参与判断。
 */
import { onMounted } from 'vue'

import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { initTheme } from '@/composables/useTheme'
import CommandPalette from '@/components/command/CommandPalette.vue'

// 应用启动即初始化主题（读 localStorage + 监听系统切换），仅此一次。
onMounted(() => {
  initTheme()
})
</script>

<template>
  <el-config-provider :locale="zhCn">
    <router-view />
    <CommandPalette />
  </el-config-provider>
</template>
