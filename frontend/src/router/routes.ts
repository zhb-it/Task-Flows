/**
 * 路由表（前端规格 §5 系统整体页面结构 / §36 路由权限 / §74 路由懒加载）。
 *
 * 结构分三块：
 *
 * - `AuthLayout` 子树：登录 / 注册，**不需要**登录（`requiresAuth: false`）。
 * - `BasicLayout` 子树：系统主框架，**需要**登录（`requiresAuth: true`）。
 * - 错误页：独立路由，不带布局，避免「未登录时看到 404 又被跳去登录页」。
 *
 * 命名与路径的对应关系见 `docs/FRONTEND_API_MAPPING.md`。
 *
 * ⚠ 两个路由的落地方式与规格目录不完全一致，原因写在对应注释里：
 * `/tasks` 与 `/tasks/board` 的页面需要「项目上下文」才能工作，因为后端
 * `GET /tasks` 把 `project_id` 列为**必填**查询参数（`app/api/v1/tasks.py`）。
 */

import type { RouteRecordRaw } from 'vue-router'

/** 站点名（同时用于标签页标题与侧边栏 Logo）。 */
export const APP_TITLE = import.meta.env.VITE_APP_TITLE || 'TaskFlow Pro'

/** 侧边栏菜单项（规格 §6 的导航顺序）。 */
export interface MenuItem {
  path: string
  title: string
  icon: string
  /**
   * 持有其中任一权限（OR 语义）才显示菜单项（TASK-084）。不写 = 所有登录
   * 用户可见。数据源是 `/users/me/permissions` 的真实权限集合；集合为空
   * （拉取失败）时该项隐藏——菜单隐藏只管入口观感，页面本身仍由后端 403
   * 兜底（规格 §35「隐藏按钮 ≠ 安全」）。
   */
  requiresAnyPermission?: string[]
}

export const MENU_ITEMS: readonly MenuItem[] = [
  { path: '/dashboard', title: '首页', icon: 'HomeFilled' },
  { path: '/tasks', title: '我的任务', icon: 'Tickets' },
  { path: '/projects', title: '项目', icon: 'FolderOpened' },
  { path: '/teams', title: '团队', icon: 'UserFilled' },
  { path: '/notifications', title: '通知', icon: 'Bell' },
  { path: '/logs', title: '操作日志', icon: 'Document' },
  {
    path: '/permissions',
    title: '权限管理',
    icon: 'Lock',
    requiresAnyPermission: ['user:update'],
  },
]

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    component: () => import('@/layouts/AuthLayout.vue'),
    meta: { requiresAuth: false },
    children: [
      {
        path: '',
        name: 'login',
        component: () => import('@/views/auth/Login.vue'),
        meta: { title: '登录' },
      },
    ],
  },
  {
    path: '/register',
    component: () => import('@/layouts/AuthLayout.vue'),
    meta: { requiresAuth: false },
    children: [
      {
        path: '',
        name: 'register',
        component: () => import('@/views/auth/Register.vue'),
        meta: { title: '注册' },
      },
    ],
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    meta: { requiresAuth: true },
    redirect: { name: 'dashboard' },
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/dashboard/Dashboard.vue'),
        meta: { title: '首页', icon: 'HomeFilled', inMenu: true },
      },
      {
        // 规格 §5 的「我的任务」。后端 `GET /tasks` 要求 `project_id` 必填，
        // 所以真正的列表必须是「项目上下文内」的页面 —— 这里先占位，
        // 由前端阶段 8（任务模块）确定交互形态后再实现。
        path: 'tasks',
        name: 'task-list',
        component: () => import('@/views/task/TaskList.vue'),
        meta: { title: '我的任务', icon: 'Tickets', inMenu: true },
      },
      {
        path: 'tasks/board',
        name: 'task-board',
        component: () => import('@/views/task/TaskBoard.vue'),
        meta: { title: '任务看板' },
      },
      {
        path: 'tasks/create',
        name: 'task-create',
        component: () => import('@/views/task/TaskCreate.vue'),
        meta: { title: '新建任务' },
      },
      {
        path: 'tasks/:taskId',
        name: 'task-detail',
        component: () => import('@/views/task/TaskDetail.vue'),
        props: true,
        meta: { title: '任务详情' },
      },
      {
        path: 'projects',
        name: 'project-list',
        component: () => import('@/views/project/ProjectList.vue'),
        meta: { title: '项目', icon: 'FolderOpened', inMenu: true },
      },
      {
        path: 'projects/:projectId',
        name: 'project-detail',
        component: () => import('@/views/project/ProjectDetail.vue'),
        props: true,
        meta: { title: '项目详情' },
      },
      {
        path: 'projects/:projectId/settings',
        name: 'project-settings',
        component: () => import('@/views/project/ProjectSettings.vue'),
        props: true,
        meta: { title: '项目设置' },
      },
      {
        path: 'teams',
        name: 'team-list',
        component: () => import('@/views/team/TeamList.vue'),
        meta: { title: '团队', icon: 'UserFilled', inMenu: true },
      },
      {
        path: 'teams/:teamId',
        name: 'team-detail',
        component: () => import('@/views/team/TeamDetail.vue'),
        props: true,
        meta: { title: '团队详情' },
      },
      {
        path: 'teams/:teamId/members',
        name: 'team-members',
        component: () => import('@/views/team/TeamMembers.vue'),
        props: true,
        meta: { title: '成员管理' },
      },
      {
        path: 'notifications',
        name: 'notification-list',
        component: () => import('@/views/notification/NotificationList.vue'),
        meta: { title: '通知', icon: 'Bell', inMenu: true },
      },
      {
        path: 'logs',
        name: 'operation-log-list',
        component: () => import('@/views/operation-log/OperationLogList.vue'),
        meta: { title: '操作日志', icon: 'Document', inMenu: true },
      },
      {
        // TASK-084：权限管理（用户-角色分配 + 权限矩阵）。路由本身不做权限
        // 拦截——页面内按 `can('user:update')` 决定加载管理区，矩阵 403 时
        // 诚实降级提示（规格 §35：真正的裁决在后端）。
        path: 'permissions',
        name: 'permission-manage',
        component: () => import('@/views/permission/PermissionManage.vue'),
        meta: { title: '权限管理', icon: 'Lock', inMenu: true },
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/profile/Profile.vue'),
        meta: { title: '个人中心', icon: 'Setting', inMenu: true },
      },
    ],
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/error/403.vue'),
    meta: { title: '没有权限', requiresAuth: false },
  },
  {
    path: '/500',
    name: 'server-error',
    component: () => import('@/views/error/500.vue'),
    meta: { title: '服务器异常', requiresAuth: false },
  },
  {
    // catch-all 必须放在最后：vue-router 4 会按路径评分排序，但显式放最后
    // 能让「新增路由」的人一眼看到它，避免误以为可以插在中间。
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/error/404.vue'),
    meta: { title: '页面不存在', requiresAuth: false },
  },
]
