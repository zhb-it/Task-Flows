/**
 * 应用入口。
 *
 * 引入顺序即依赖顺序：样式 → 应用壳 → Pinia → Router → UI 库。
 *
 * 关于 Element Plus 的引入方式：`unplugin-vue-components` 那套按需引入需要额外的
 * 构建插件与配置，本项目规模下全量引入的代价只是产物体积（见 README「已知取舍」），
 * 换来的是「不用为每个组件写 import」的简单性。规格 §74 反对的是「为优化而过早
 * 引入复杂方案」，这里按同一原则选择简单的做法。
 *
 * 图标**不做全量全局注册**：`@element-plus/icons-vue` 有 300+ 个图标，全量注册会
 * 让它们全部进入产物。各组件按需 `import { Bell } from '@element-plus/icons-vue'`。
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import 'element-plus/dist/index.css'
import '@/assets/styles/index.css'

import App from '@/App.vue'
import router from '@/router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
// 中文界面：Element Plus 默认英文，分页器、日期选择器、确认框都需要中文文案。
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
