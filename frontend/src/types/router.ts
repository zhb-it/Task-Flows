/**
 * 路由 meta 的类型扩展（前端规格 §36 / §73）。
 *
 * 让 `to.meta.title` / `to.meta.requiresAuth` 具备类型，避免守卫里到处写
 * `as string`。vue-router 的 meta 在嵌套路由下是**合并**的：`to.meta` 同时包含
 * 所有 matched 记录的 meta，子路由同名字段覆盖父路由。
 */

import 'vue-router'

declare module 'vue-router' {
  interface RouteMeta {
    /** 页面标题：用于浏览器标签页与面包屑。 */
    title?: string
    /**
     * 是否需要登录。放在**父路由**上表达整棵子树的要求：
     * `BasicLayout`（系统主框架）为 true，`AuthLayout`（登录/注册）为 false。
     */
    requiresAuth?: boolean
    /** 侧边栏图标名（已全局注册的 Element Plus 图标组件名）。 */
    icon?: string
    /**
     * 是否出现在侧边栏。默认不出现在菜单里（详情页、错误页都不需要菜单项）。
     */
    inMenu?: boolean
  }
}
