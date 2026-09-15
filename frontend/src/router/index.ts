/**
 * 路由实例（前端规格 §36）。
 *
 * 用 HTML5 History 模式（`createWebHistory`）而不是 hash：地址更干净，代价是
 * 生产环境需要 Nginx 把未知路径回落到 `index.html`（规格 §56 的 Nginx 配置，
 * 属前端阶段 15「Docker / Nginx」的交付内容）。
 */

import { createRouter, createWebHistory } from 'vue-router'

import { registerGuards } from '@/router/guards'
import { routes } from '@/router/routes'

export const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  // 切换路由时回到顶部：从长列表点进详情页却停在半页的位置很突兀。
  scrollBehavior: () => ({ top: 0 }),
})

registerGuards(router)

export default router
