/**
 * 应用入口。
 *
 * 引入顺序即依赖顺序：基础样式 → 应用壳 → Pinia → Router。
 *
 * 关于 Element Plus 的引入方式（TASK-080，前端规格 §59 阶段 16 / §74
 * 「组件按需加载」）：模板组件由 `vite.config.ts` 里的 `Components()` 插件
 * 按需编译引入（含 `v-loading` 指令），入口**不再** `app.use(ElementPlus)`
 * 全量注册。代码里直接调用的命令式 API 保持显式 import，它们的样式无法被
 * 模板插件感知，在这里集中补引——只引实际用到的四个，替换掉全量 CSS。
 * 界面语言（locale）改为 `<el-config-provider>` 包裹（见 `App.vue`）。
 *
 * 图标**不做全量全局注册**：`@element-plus/icons-vue` 有 300+ 个图标，全量注册会
 * 让它们全部进入产物。各组件按需 `import { Bell } from '@element-plus/icons-vue'`。
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'

// 按需引入下的「补样式」清单：与代码里显式调用的命令式 API 一一对应。
// 新增 ElXxx 直接调用时记得在这里补一行，否则组件能弹但样式缺失。
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/notification/style/css'
import 'element-plus/es/components/loading/style/css'

import '@/assets/styles/index.css'

import App from '@/App.vue'
import router from '@/router'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
