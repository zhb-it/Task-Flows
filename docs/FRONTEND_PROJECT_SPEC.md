# 团队任务协作系统前端开发文档

> 文档版本：v1.0
> 项目名称：团队任务协作系统
> 文档类型：前端项目开发规范 / 技术设计 / 页面设计 / 开发计划
> 适用对象：开发者、AI Coding Agent、项目维护者
> 前端定位：企业级团队任务协作 Web 应用

---

# 一、项目概述

## 1.1 项目背景

团队任务协作系统是一套面向团队内部使用的任务管理平台。

系统用于解决：

* 团队成员管理
* 项目管理
* 任务创建与分配
* 任务状态流转
* 评论沟通
* 附件管理
* 消息通知
* 操作日志
* 权限控制
* 团队协作数据统计

前端负责提供完整的 Web 管理界面，通过 RESTful API 与 FastAPI 后端进行通信。

---

# 二、前端技术栈

## 2.1 核心技术

| 技术           | 版本  | 用途      |
| ------------ | --- | ------- |
| Vue          | 3.x | 前端核心框架  |
| TypeScript   | 5.x | 类型系统    |
| Vite         | 7.x | 构建工具    |
| Vue Router   | 4.x | 路由管理    |
| Pinia        | 3.x | 状态管理    |
| Axios        | 1.x | HTTP 请求 |
| Element Plus | 2.x | UI 组件库  |
| ECharts      | 5.x | 数据可视化   |
| ESLint       | -   | 代码规范    |
| Prettier     | -   | 代码格式化   |
| Vitest       | -   | 单元测试    |
| Playwright   | -   | E2E 测试  |

---

# 三、前端项目定位

前端不是简单的 CRUD 页面集合。

项目需要体现以下工程能力：

1. Vue 3 + TypeScript
2. 组件化开发
3. 路由权限控制
4. RBAC 权限控制
5. API 类型约束
6. Axios 请求封装
7. JWT Token 管理
8. Refresh Token 自动刷新
9. 全局状态管理
10. 表单校验
11. 错误处理
12. Loading 状态处理
13. 空状态处理
14. 分页
15. 搜索与筛选
16. 文件上传
17. 消息通知
18. 响应式布局
19. 单元测试
20. E2E 测试

---

# 四、前端项目目录

推荐结构：

```text
frontend/
│
├── public/
│
├── src/
│   │
│   ├── api/
│   │   ├── auth.ts
│   │   ├── user.ts
│   │   ├── team.ts
│   │   ├── project.ts
│   │   ├── task.ts
│   │   ├── comment.ts
│   │   ├── attachment.ts
│   │   ├── notification.ts
│   │   └── operation-log.ts
│   │
│   ├── assets/
│   │   ├── images/
│   │   └── styles/
│   │
│   ├── components/
│   │   ├── common/
│   │   ├── layout/
│   │   ├── task/
│   │   ├── project/
│   │   ├── team/
│   │   └── notification/
│   │
│   ├── composables/
│   │   ├── useRequest.ts
│   │   ├── usePagination.ts
│   │   ├── usePermission.ts
│   │   └── useUpload.ts
│   │
│   ├── layouts/
│   │   ├── BasicLayout.vue
│   │   └── AuthLayout.vue
│   │
│   ├── router/
│   │   ├── index.ts
│   │   ├── routes.ts
│   │   └── guards.ts
│   │
│   ├── stores/
│   │   ├── auth.ts
│   │   ├── user.ts
│   │   ├── team.ts
│   │   ├── project.ts
│   │   └── notification.ts
│   │
│   ├── types/
│   │   ├── auth.ts
│   │   ├── user.ts
│   │   ├── team.ts
│   │   ├── project.ts
│   │   ├── task.ts
│   │   ├── notification.ts
│   │   └── common.ts
│   │
│   ├── utils/
│   │   ├── request.ts
│   │   ├── auth.ts
│   │   ├── permission.ts
│   │   ├── format.ts
│   │   └── storage.ts
│   │
│   ├── views/
│   │   ├── auth/
│   │   │   ├── Login.vue
│   │   │   └── Register.vue
│   │   │
│   │   ├── dashboard/
│   │   │   └── Dashboard.vue
│   │   │
│   │   ├── team/
│   │   │   ├── TeamList.vue
│   │   │   ├── TeamDetail.vue
│   │   │   └── TeamMembers.vue
│   │   │
│   │   ├── project/
│   │   │   ├── ProjectList.vue
│   │   │   ├── ProjectDetail.vue
│   │   │   └── ProjectSettings.vue
│   │   │
│   │   ├── task/
│   │   │   ├── TaskList.vue
│   │   │   ├── TaskBoard.vue
│   │   │   ├── TaskDetail.vue
│   │   │   └── TaskCreate.vue
│   │   │
│   │   ├── notification/
│   │   │   └── NotificationList.vue
│   │   │
│   │   ├── operation-log/
│   │   │   └── OperationLogList.vue
│   │   │
│   │   ├── profile/
│   │   │   └── Profile.vue
│   │   │
│   │   └── error/
│   │       ├── 403.vue
│   │       └── 404.vue
│   │
│   ├── App.vue
│   ├── main.ts
│   └── env.d.ts
│
├── tests/
│   ├── unit/
│   └── e2e/
│
├── .env.development
├── .env.production
├── .gitignore
├── eslint.config.js
├── prettier.config.js
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

---

# 五、系统整体页面结构

系统采用：

```text
登录页
   ↓
系统主框架
   ├── 首页 Dashboard
   ├── 我的任务
   ├── 项目
   │    ├── 项目列表
   │    ├── 项目详情
   │    └── 项目设置
   ├── 团队
   │    ├── 团队列表
   │    ├── 团队详情
   │    └── 成员管理
   ├── 通知
   ├── 操作日志
   └── 个人中心
```

---

# 六、整体 UI 布局

采用经典后台管理系统布局。

```text
┌──────────────────────────────────────────────┐
│ Logo       团队任务协作系统       用户  🔔   │
├──────────┬───────────────────────────────────┤
│          │                                   │
│ 首页     │                                   │
│ 我的任务 │          页面内容区域             │
│ 项目     │                                   │
│ 团队     │                                   │
│ 通知     │                                   │
│ 操作日志 │                                   │
│          │                                   │
│          │                                   │
└──────────┴───────────────────────────────────┘
```

---

# 七、登录模块

## 7.1 登录页面

路由：

```text
/login
```

页面内容：

```text
┌────────────────────────────┐
│                            │
│       团队任务协作系统       │
│                            │
│  用户名                     │
│  ┌──────────────────────┐  │
│  │                      │  │
│  └──────────────────────┘  │
│                            │
│  密码                       │
│  ┌──────────────────────┐  │
│  │                  👁   │  │
│  └──────────────────────┘  │
│                            │
│  [        登录        ]     │
│                            │
│  没有账号？立即注册          │
│                            │
└────────────────────────────┘
```

功能：

* 用户名输入
* 密码输入
* 表单验证
* 登录 Loading
* 登录失败提示
* Token 保存
* 获取当前用户
* 跳转 Dashboard

---

# 八、注册模块

路由：

```text
/register
```

字段：

* 用户名
* 邮箱
* 密码
* 确认密码

校验：

```text
用户名不能为空
邮箱格式正确
密码长度符合后端要求
两次密码一致
```

注册成功：

```text
注册成功 → 跳转登录页
```

---

# 九、认证状态管理

使用 Pinia：

```text
stores/auth.ts
```

负责：

```text
accessToken
refreshToken
currentUser
isAuthenticated
login()
logout()
refreshAccessToken()
fetchCurrentUser()
```

---

# 十、JWT Token 管理

前端请求：

```text
Authorization: Bearer <access_token>
```

Axios Request Interceptor：

```text
发送请求
   ↓
检查 access_token
   ↓
添加 Authorization
   ↓
发送请求
```

遇到：

```text
401 Unauthorized
```

执行：

```text
access_token 过期
       ↓
使用 refresh_token
       ↓
请求刷新接口
       ↓
获得新的 access_token
       ↓
重新执行原请求
```

如果 Refresh Token 也失效：

```text
清除认证信息
↓
跳转 /login
```

---

# 十一、首页 Dashboard

路由：

```text
/dashboard
```

页面用于展示团队和任务概况。

---

## 11.1 数据卡片

顶部：

```text
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ 项目数量 │ │ 任务总数 │ │ 进行中   │ │ 已完成   │
│   12     │ │   128    │ │   35     │ │   82     │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## 11.2 任务统计

使用 ECharts。

展示：

```text
任务状态统计
├── 待处理
├── 进行中
├── 待审核
├── 已完成
└── 已取消
```

---

## 11.3 最近任务

展示：

| 任务 | 项目 | 负责人 | 状态 | 截止时间 |
| -- | -- | --- | -- | ---- |

---

## 11.4 最近通知

展示：

```text
任务被分配给你
任务状态发生变化
有人评论了你的任务
项目邀请
系统通知
```

---

# 十二、团队模块

## 12.1 团队列表

路由：

```text
/teams
```

功能：

* 团队列表
* 创建团队
* 搜索团队
* 查看团队
* 团队成员数量
* 创建时间

---

# 十三、团队详情

路由：

```text
/teams/:teamId
```

页面：

```text
团队名称
团队描述

成员
项目
任务统计
团队设置
```

---

# 十四、团队成员管理

路由：

```text
/teams/:teamId/members
```

展示：

| 用户 | 邮箱 | 团队角色 | 加入时间 | 操作 |
| -- | -- | ---- | ---- | -- |

支持：

* 邀请成员
* 修改角色
* 移除成员
* 查看成员

---

# 十五、团队邀请

邀请成员：

```text
邮箱
角色
```

提交：

```text
POST /teams/{team_id}/members/invite
```

成功后：

```text
邀请成功
```

---

# 十六、项目模块

## 16.1 项目列表

路由：

```text
/projects
```

支持：

* 项目搜索
* 创建项目
* 状态筛选
* 所属团队筛选
* 分页

项目卡片：

```text
┌──────────────────────────┐
│ 项目名称                 │
│ 项目描述                 │
│                          │
│ 成员：12                 │
│ 任务：56                 │
│                          │
│ ███████████░░ 78%        │
│                          │
│ 查看项目                 │
└──────────────────────────┘
```

---

# 十七、创建项目

字段：

```text
项目名称
项目描述
所属团队
```

前端进行：

* 必填校验
* 长度校验
* 提交 Loading
* 成功提示
* 失败提示

---

# 十八、项目详情

路由：

```text
/projects/:projectId
```

页面：

```text
项目名称
项目描述

[任务列表] [任务看板] [项目成员] [项目设置]
```

---

# 十九、任务模块

任务模块是系统核心功能。

---

# 二十、任务列表

路由：

```text
/tasks
```

支持：

```text
关键词搜索
项目筛选
状态筛选
优先级筛选
负责人筛选
创建时间筛选
分页
```

页面：

```text
┌──────────────────────────────────────────┐
│ 我的任务                                 │
│                                          │
│ [搜索任务] [状态▼] [优先级▼] [搜索]      │
│                                          │
│ ┌──────────────────────────────────────┐ │
│ │ 任务名称 │ 优先级 │ 状态 │ 负责人    │ │
│ ├──────────────────────────────────────┤ │
│ │ 完成登录 │ 高     │ 进行中 │ 张三     │ │
│ │ 完成接口 │ 中     │ 待审核 │ 李四     │ │
│ └──────────────────────────────────────┘ │
└──────────────────────────────────────────┘
```

---

# 二十一、任务状态

后端状态：

```text
TODO
IN_PROGRESS
REVIEW
DONE
CANCELLED
```

前端显示：

```text
TODO          → 待处理
IN_PROGRESS   → 进行中
REVIEW        → 待审核
DONE          → 已完成
CANCELLED     → 已取消
```

---

# 二十二、任务优先级

```text
LOW       → 低
MEDIUM    → 中
HIGH      → 高
```

前端必须统一使用枚举。

禁止在不同页面自行定义状态文本。

统一：

```text
types/task.ts
```

或者：

```text
constants/task.ts
```

---

# 二十三、任务看板

路由：

```text
/tasks/board
```

采用 Kanban 看板。

```text
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│  待处理    │ │   进行中   │ │   待审核   │ │   已完成   │
│            │ │            │ │            │ │            │
│ ┌────────┐ │ │ ┌────────┐ │ │ ┌────────┐ │ │ ┌────────┐ │
│ │任务 A  │ │ │ │任务 B  │ │ │ │任务 C  │ │ │ │任务 D  │ │
│ └────────┘ │ │ └────────┘ │ │ └────────┘ │ │ └────────┘ │
│            │ │            │ │            │ │            │
└────────────┘ └────────────┘ └────────────┘ └────────────┘
```

---

# 二十四、任务状态流转

前端不能自行决定任务状态是否允许修改。

状态规则由后端 Service 层最终控制。

前端只负责：

```text
显示合法操作
↓
用户点击
↓
调用 API
↓
后端验证
↓
成功后更新 UI
```

合法状态：

```text
TODO
 ↓
IN_PROGRESS
 ↓
REVIEW
 ↓
DONE
```

允许：

```text
任意状态 → CANCELLED
```

禁止：

```text
DONE → TODO
```

前端即使隐藏非法操作，也不能替代后端权限和状态校验。

---

# 二十五、任务详情

路由：

```text
/tasks/:taskId
```

页面：

```text
任务标题
任务描述

状态
优先级
创建人
负责人
截止时间
创建时间
更新时间

任务操作

评论
附件
操作记录
```

---

# 二十六、任务创建

字段：

```text
任务标题
任务描述
项目
优先级
负责人
截止时间
```

表单要求：

```text
标题必填
项目必填
优先级必填
截止时间格式正确
负责人必须属于对应团队/项目
```

最终合法性由后端验证。

---

# 二十七、任务编辑

允许编辑：

```text
标题
描述
优先级
负责人
截止时间
```

是否允许编辑由后端权限决定。

---

# 二十八、任务评论

任务详情页面提供评论区域。

```text
┌──────────────────────────────┐
│ 评论                         │
│                              │
│ 张三                         │
│ 这个接口已经完成             │
│ 2026-09-13 15:20             │
│                              │
│ 李四                         │
│ 收到                         │
│                              │
│ ┌──────────────────────────┐ │
│ │ 输入评论...              │ │
│ └──────────────────────────┘ │
│              [发表评论]       │
└──────────────────────────────┘
```

支持：

* 查看评论
* 添加评论
* 删除自己的评论

---

# 二十九、附件模块

任务支持附件上传。

前端功能：

```text
选择文件
↓
检查文件大小
↓
检查文件类型
↓
上传
↓
显示进度
↓
上传成功
```

附件列表：

```text
文件名
文件大小
上传者
上传时间
下载
删除
```

文件实际存储与权限由后端负责。

前端不能假设文件一定上传成功。

---

# 三十、通知模块

路由：

```text
/notifications
```

通知类型：

```text
TASK_ASSIGNED
TASK_STATUS_CHANGED
TASK_COMMENTED
TEAM_INVITED
SYSTEM
```

页面：

```text
全部
未读
已读
```

支持：

* 查看通知
* 标记已读
* 全部标记已读
* 点击通知跳转对应资源

例如：

```text
你被分配了任务「完成登录接口」
↓
点击
↓
/tasks/123
```

---

# 三十一、顶部消息通知

系统顶部导航显示：

```text
🔔
```

如果存在未读通知：

```text
🔔  5
```

点击：

```text
查看最近通知
```

---

# 三十二、操作日志

路由：

```text
/operation-logs
```

管理员或者拥有相关权限的用户可以查看。

展示：

| 操作人 | 操作 | 资源 | IP | 时间 |
| --- | -- | -- | -- | -- |

支持：

* 时间筛选
* 操作人筛选
* 操作类型筛选
* 分页

---

# 三十三、个人中心

路由：

```text
/profile
```

显示：

```text
头像
用户名
邮箱
创建时间
```

功能：

```text
修改个人信息
修改密码
退出登录
```

---

# 三十四、RBAC 前端权限

系统采用 RBAC。

权限示例：

```text
user:read
user:update

team:create
team:read
team:update
team:delete

project:create
project:read
project:update
project:delete

task:create
task:read
task:update
task:delete
task:assign

comment:create
comment:delete

attachment:upload
attachment:delete

operation_log:read
```

---

# 三十五、权限控制原则

前端权限控制只负责：

```text
页面展示
按钮展示
交互体验
路由访问
```

后端权限控制负责：

```text
真正的数据安全
```

例如：

```vue
<el-button
  v-if="hasPermission('task:update')"
>
  编辑任务
</el-button>
```

但是：

```text
隐藏按钮 ≠ 安全
```

真正 API 权限必须由后端验证。

---

# 三十六、路由权限

路由：

```text
router/guards.ts
```

流程：

```text
访问页面
 ↓
是否登录？
 ↓
否 → /login
 ↓
是
 ↓
检查页面权限
 ↓
无权限 → /403
 ↓
有权限 → 页面
```

---

# 三十七、Axios 请求封装

统一：

```text
src/utils/request.ts
```

所有业务 API：

```text
src/api/
```

禁止在 Vue 页面中直接大量编写：

```text
axios.get(...)
axios.post(...)
```

应该：

```text
View
 ↓
API
 ↓
request
 ↓
Axios
 ↓
FastAPI
```

---

# 三十八、API 模块规范

例如：

```text
api/task.ts
```

负责：

```text
getTasks()
getTask()
createTask()
updateTask()
deleteTask()
changeTaskStatus()
assignTask()
```

页面只调用：

```text
taskApi.getTasks()
```

不直接处理 HTTP 细节。

---

# 三十九、TypeScript 类型规范

API 数据必须定义类型。

例如：

```text
Task
TaskStatus
TaskPriority
TaskListParams
CreateTaskRequest
UpdateTaskRequest
TaskListResponse
```

禁止大量：

```typescript
any
```

优先使用：

```typescript
unknown
```

并通过类型收窄处理。

---

# 四十、统一 API 响应

如果后端统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

前端统一处理。

不要每个页面重复：

```text
if response.code...
```

---

# 四十一、错误处理

需要处理：

```text
400
401
403
404
409
422
429
500
```

对应：

```text
400 → 请求参数错误
401 → 登录失效
403 → 没有权限
404 → 数据不存在
409 → 数据冲突
422 → 参数校验失败
429 → 请求过于频繁
500 → 服务器异常
```

---

# 四十二、Loading 状态

所有异步操作都必须考虑 Loading。

例如：

```text
登录
创建任务
编辑任务
删除任务
上传文件
修改状态
发表评论
```

禁止用户连续点击造成重复请求。

---

# 四十三、空状态

列表没有数据时：

```text
暂无任务
```

不要出现：

```text
空白页面
```

例如：

```text
暂无任务

[创建任务]
```

---

# 四十四、确认操作

危险操作必须二次确认。

例如：

```text
删除任务
删除项目
删除成员
删除附件
取消任务
```

使用：

```text
ElMessageBox.confirm()
```

---

# 四十五、表单设计

统一：

```text
label
required
placeholder
error message
loading
disabled
```

表单提交：

```text
用户输入
 ↓
前端校验
 ↓
发送 API
 ↓
后端校验
 ↓
成功
 ↓
刷新数据
```

---

# 四十六、分页

统一分页组件：

```text
src/components/common/AppPagination.vue
```

支持：

```text
page
pageSize
total
```

默认：

```text
page = 1
pageSize = 20
```

具体值必须与后端 API 契约保持一致。

---

# 四十七、搜索与筛选

列表页面统一采用：

```text
搜索框
筛选条件
查询按钮
重置按钮
```

例如：

```text
关键词： [____________]

状态：   [全部 ▼]

优先级： [全部 ▼]

负责人： [全部 ▼]

[查询] [重置]
```

---

# 四十八、数据刷新原则

创建、修改、删除成功后：

优先：

```text
重新请求当前列表
```

而不是大量手动修改本地状态。

原因：

```text
保证前端数据与后端数据库最终一致
```

对于明显需要即时体验的局部数据，可以进行乐观更新，但必须考虑失败回滚。

---

# 四十九、组件设计原则

组件分为：

```text
页面组件
业务组件
通用组件
```

例如：

```text
views/task/TaskList.vue
```

负责页面。

```text
components/task/TaskCard.vue
```

负责任务卡片。

```text
components/common/AppPagination.vue
```

负责通用分页。

---

# 五十、禁止的组件设计

禁止：

```text
一个 Vue 文件超过几百行后继续无限堆代码
```

如果页面过于复杂，需要拆分：

```text
TaskList.vue
TaskFilter.vue
TaskTable.vue
TaskCreateDialog.vue
TaskDetailDrawer.vue
```

---

# 五十一、状态管理原则

Pinia 主要保存：

```text
登录用户
Token
用户权限
当前团队
当前项目
通知状态
```

不建议把所有页面数据都放进 Pinia。

例如：

```text
任务列表
评论列表
项目列表
```

默认由页面自身管理。

---

# 五十二、缓存策略

可以缓存：

```text
当前用户
权限
团队基础信息
项目基础信息
```

不建议长期缓存：

```text
任务列表
通知列表
评论
操作日志
```

这些数据需要保持较高的新鲜度。

---

# 五十三、文件上传安全

前端可以检查：

```text
文件大小
文件扩展名
MIME 类型
```

但是前端检查不能替代后端安全检查。

后端必须重新验证。

---

# 五十四、环境变量

开发环境：

```text
.env.development
```

示例：

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

生产环境：

```text
.env.production
```

示例：

```env
VITE_API_BASE_URL=/api/v1
```

禁止把：

```text
数据库密码
JWT Secret
Redis 密码
服务器密码
```

放入前端环境变量。

因为前端环境变量最终可能进入浏览器。

---

# 五十五、开发环境代理

Vite 开发环境建议：

```text
浏览器
 ↓
Vite Dev Server
 ↓
/api
 ↓
FastAPI
```

例如：

```text
http://localhost:5173
```

API：

```text
http://localhost:5173/api/v1
```

代理到：

```text
http://localhost:8000/api/v1
```

---

# 五十六、生产环境架构

推荐：

```text
Internet
   ↓
Nginx
   ├── /          → Vue 静态文件
   │
   └── /api/      → FastAPI
                    ↓
                 PostgreSQL
                    ↓
                   Redis
                    ↓
                  Celery
```

---

# 五十七、前后端接口契约

前端必须严格根据：

```text
docs/API_CONTRACT.md
```

调用 API。

禁止：

```text
猜测 API
猜测字段
猜测状态
猜测返回结构
```

如果 API 文档与后端代码不一致：

```text
停止当前任务
↓
确认真实 API
↓
更新 API_CONTRACT.md
↓
继续开发
```

---

# 五十八、页面与 API 映射

| 页面       | 主要 API                    |
| -------- | ------------------------- |
| 登录       | `/auth/login`             |
| 注册       | `/auth/register`          |
| 当前用户     | `/auth/me`                |
| Token 刷新 | `/auth/refresh`           |
| 团队       | `/teams`                  |
| 团队成员     | `/teams/{id}/members`     |
| 项目       | `/projects`               |
| 任务       | `/tasks`                  |
| 任务详情     | `/tasks/{id}`             |
| 评论       | `/tasks/{id}/comments`    |
| 附件       | `/tasks/{id}/attachments` |
| 通知       | `/notifications`          |
| 操作日志     | `/operation-logs`         |

具体 URL、参数、响应结构必须以实际后端 API 契约为准。

---

# 五十九、前端开发顺序

不要一次生成整个前端。

采用：

```text
阶段 1
项目初始化

↓

阶段 2
基础布局

↓

阶段 3
登录 / 注册

↓

阶段 4
JWT / 用户状态

↓

阶段 5
Dashboard

↓

阶段 6
团队

↓

阶段 7
项目

↓

阶段 8
任务

↓

阶段 9
评论

↓

阶段 10
附件

↓

阶段 11
通知

↓

阶段 12
权限

↓

阶段 13
操作日志

↓

阶段 14
测试

↓

阶段 15
Docker / Nginx

↓

阶段 16
优化
```

---

# 六十、第一阶段：项目初始化

目标：

```text
创建 Vue 3 + TypeScript + Vite 项目
```

完成：

```text
Vue
TypeScript
Vite
Vue Router
Pinia
Axios
Element Plus
ESLint
Prettier
```

验证：

```text
npm install
npm run dev
```

页面正常打开。

---

# 六十一、第二阶段：基础框架

完成：

```text
App.vue
BasicLayout
AuthLayout
Header
Sidebar
Breadcrumb
UserMenu
NotificationBell
```

实现：

```text
侧边栏
顶部导航
用户信息
退出登录
路由切换
```

---

# 六十二、第三阶段：认证

完成：

```text
Login
Register
Auth Store
Axios Interceptor
Route Guard
Token Refresh
Logout
```

必须完成真实后端接口联调。

---

# 六十三、第四阶段：Dashboard

完成：

```text
统计卡片
任务统计
最近任务
最近通知
```

---

# 六十四、第五阶段：团队

完成：

```text
团队列表
创建团队
团队详情
成员列表
邀请成员
修改角色
移除成员
```

---

# 六十五、第六阶段：项目

完成：

```text
项目列表
创建项目
项目详情
项目设置
```

---

# 六十六、第七阶段：任务

这是前端最重要的模块。

完成：

```text
任务列表
任务搜索
任务筛选
任务分页
任务创建
任务编辑
任务详情
任务状态修改
任务分配
任务看板
```

---

# 六十七、第八阶段：评论与附件

完成：

```text
评论列表
发表评论
删除评论
附件上传
附件列表
附件下载
附件删除
```

---

# 六十八、第九阶段：通知

完成：

```text
通知列表
未读数量
标记已读
全部已读
通知跳转
```

---

# 六十九、第十阶段：权限

完成：

```text
路由权限
菜单权限
按钮权限
用户角色
权限判断
403 页面
```

---

# 七十、第十一阶段：日志

完成：

```text
操作日志列表
筛选
分页
详情
```

---

# 七十一、第十二阶段：测试

## 单元测试

重点：

```text
utils
composables
stores
permission
format
```

---

## 组件测试

重点：

```text
Login
TaskForm
TaskCard
TaskFilter
Pagination
```

---

## E2E 测试

核心流程：

```text
注册
 ↓
登录
 ↓
进入 Dashboard
 ↓
创建团队
 ↓
创建项目
 ↓
创建任务
 ↓
分配任务
 ↓
修改任务状态
 ↓
发表评论
 ↓
查看通知
 ↓
退出登录
```

---

# 七十二、错误页面

必须提供：

```text
403.vue
404.vue
500.vue
```

403：

```text
没有权限访问该页面

[返回首页]
```

404：

```text
页面不存在

[返回首页]
```

---

# 七十三、响应式设计

主要支持：

```text
1920 × 1080
1440 × 900
1366 × 768
1280 × 720
```

同时考虑：

```text
平板
较小屏幕
```

重点：

```text
Sidebar
Table
Task Board
Dashboard
```

---

# 七十四、前端性能要求

注意：

```text
路由懒加载
组件按需加载
图片压缩
避免无意义重复请求
避免大型组件重复渲染
合理使用 computed
合理使用 watch
```

不要为了“优化”而过早引入复杂缓存方案。

---

# 七十五、代码规范

## Vue

推荐：

```vue
<script setup lang="ts">
```

---

## TypeScript

优先：

```typescript
interface
type
enum / union type
```

禁止无理由使用：

```typescript
any
```

---

# 七十六、命名规范

组件：

```text
PascalCase
```

例如：

```text
TaskCard.vue
TaskForm.vue
```

变量：

```text
camelCase
```

例如：

```text
taskList
currentUser
```

API：

```text
camelCase
```

例如：

```text
getTaskList()
createTask()
```

---

# 七十七、Git 提交规范

推荐：

```text
feat: 新增任务看板
fix: 修复任务状态刷新问题
refactor: 重构任务 API
test: 增加任务组件测试
docs: 更新前端开发文档
style: 调整任务列表样式
chore: 更新依赖
```

---

# 七十八、前端与后端开发协作规则

前端开发不能脱离后端 API 契约。

开发流程：

```text
阅读 PROJECT_SPEC.md
        ↓
阅读 API_CONTRACT.md
        ↓
确认对应后端接口
        ↓
设计页面
        ↓
实现 API 类型
        ↓
实现 API
        ↓
实现组件
        ↓
实现页面
        ↓
联调
        ↓
测试
        ↓
更新 PROGRESS.md
```

---

# 七十九、AI Coding 开发规则

如果使用 Cursor / Claude Code / 其他 AI Coding Agent：

## 规则 1

AI 必须先阅读：

```text
PROJECT_SPEC.md
ARCHITECTURE.md
API_CONTRACT.md
DB_SCHEMA.md
TASKS.md
PROGRESS.md
```

---

## 规则 2

AI 不允许：

```text
一次性生成整个前端项目
```

必须：

```text
一个阶段
↓
一个任务
↓
实现
↓
验证
↓
记录
↓
下一个任务
```

---

## 规则 3

AI 不允许：

```text
自行猜测后端 API
```

如果接口不存在：

```text
停止
说明缺失内容
等待确认
```

---

## 规则 4

AI 不允许：

```text
擅自更换 Vue 技术栈
擅自引入大型依赖
擅自修改项目架构
擅自修改 API 契约
```

---

## 规则 5

AI 修改代码后必须告诉开发者：

```text
修改了什么
为什么修改
涉及哪些文件
如何验证
下一步是什么
```

---

# 八十、前端任务驱动开发

TASKS.md 示例：

```text
## Frontend Phase 1

- [ ] 初始化 Vue + TypeScript + Vite
- [ ] 安装 Element Plus
- [ ] 配置 Router
- [ ] 配置 Pinia
- [ ] 配置 Axios
- [ ] 配置 ESLint
- [ ] 配置 Prettier
- [ ] 创建基础目录

## Frontend Phase 2

- [ ] 创建 AuthLayout
- [ ] 创建 BasicLayout
- [ ] 创建 Sidebar
- [ ] 创建 Header
- [ ] 创建 Breadcrumb

## Frontend Phase 3

- [ ] Login 页面
- [ ] Register 页面
- [ ] Auth Store
- [ ] Token 管理
- [ ] Axios 拦截器
- [ ] Router Guard
```

---

# 八十一、开发完成定义

一个前端任务只有满足以下条件才能标记完成：

```text
代码完成
+
TypeScript 无明显错误
+
ESLint 通过
+
页面可以正常运行
+
API 联调成功
+
异常状态已处理
+
Loading 已处理
+
空状态已处理
+
权限已处理
+
必要测试完成
+
TASKS.md 更新
+
PROGRESS.md 更新
```

---

# 八十二、前端最终验收

## 功能

```text
□ 登录
□ 注册
□ Token 刷新
□ 退出
□ Dashboard
□ 团队管理
□ 成员管理
□ 项目管理
□ 任务管理
□ 任务看板
□ 任务状态流转
□ 评论
□ 附件
□ 通知
□ 操作日志
□ 权限控制
```

---

## 工程

```text
□ TypeScript
□ ESLint
□ Prettier
□ Axios 封装
□ Pinia
□ Router Guard
□ API 类型
□ 组件拆分
□ 错误处理
□ Loading
□ Empty State
```

---

## 测试

```text
□ 单元测试
□ 组件测试
□ E2E 测试
□ 登录流程
□ 创建任务流程
□ 修改任务状态流程
□ 权限流程
```

---

# 八十三、最终前后端完整架构

最终项目：

```text
                    用户浏览器
                         │
                         ▼
                ┌─────────────────┐
                │ Vue 3 + TS      │
                │ Element Plus    │
                │ Pinia           │
                │ Vue Router      │
                └────────┬────────┘
                         │
                       HTTP
                         │
                         ▼
                ┌─────────────────┐
                │     Nginx       │
                └────────┬────────┘
                         │
                         ▼
                ┌─────────────────┐
                │     FastAPI     │
                │                 │
                │ Router          │
                │ Service         │
                │ CRUD            │
                │ Model           │
                └──────┬─────┬────┘
                       │     │
             ┌─────────┘     └─────────┐
             ▼                         ▼
      ┌─────────────┐           ┌─────────────┐
      │ PostgreSQL  │           │    Redis    │
      └─────────────┘           └──────┬──────┘
                                       │
                                       ▼
                                ┌─────────────┐
                                │   Celery    │
                                └─────────────┘
```

---

# 八十四、前端最终目标

本项目最终不是追求“页面多”。

而是通过这个项目体现：

```text
Vue 3 工程化
+
TypeScript
+
组件化
+
状态管理
+
路由权限
+
RBAC
+
JWT
+
API 封装
+
异步任务交互
+
文件上传
+
数据可视化
+
测试
+
Docker
+
前后端联调
```

最终应形成一个：

```text
可以运行
可以演示
可以部署
可以测试
可以维护
可以解释
```

的完整前后端项目。

---

# 八十五、与后端项目文档的关系

本文件负责：

```text
前端怎么做
```

后端项目开发文档负责：

```text
后端怎么做
```

API_CONTRACT.md 负责：

```text
前后端怎么对接
```

ARCHITECTURE.md 负责：

```text
整个系统怎么组织
```

TASKS.md 负责：

```text
现在具体做什么
```

PROGRESS.md 负责：

```text
已经做到哪里
```

因此整个项目开发体系：

```text
PROJECT_SPEC.md
        │
        ├── ARCHITECTURE.md
        │
        ├── DB_SCHEMA.md
        │
        ├── API_CONTRACT.md
        │
        ├── FRONTEND_PROJECT_SPEC.md
        │
        ├── TASKS.md
        │
        └── PROGRESS.md
```

其中：

```text
FRONTEND_PROJECT_SPEC.md
```

是前端的核心开发说明。

---

# 八十六、最终开发原则

> 不追求一次生成完整项目。
>
> 先设计，再实现。
>
> 先接口，再页面。
>
> 先最小可运行版本，再逐步完善。
>
> 每完成一个功能，都必须验证。
>
> 每次修改，都必须知道为什么修改。
>
> AI 是开发助手，不是黑箱代码生成器。
>
> 后端负责最终的数据安全和业务规则。
>
> 前端负责良好的交互、展示和用户体验。
>
> 所有最终行为以真实后端 API 和项目文档为准。

---

# 八十七、当前推荐开发起点

项目正式开始前，先完成：

```text
1. 确认前端技术栈
2. 初始化 frontend/
3. 配置 Vue 3 + TypeScript + Vite
4. 配置 Element Plus
5. 配置 Vue Router
6. 配置 Pinia
7. 配置 Axios
8. 创建基础目录
9. 创建 BasicLayout
10. 创建 AuthLayout
```

**不要立即开发 Dashboard、任务页面等业务功能。**

先把前端工程骨架搭起来，然后再进入：

```text
登录
→ JWT
→ 用户
→ Dashboard
→ 团队
→ 项目
→ 任务
```

这个顺序可以最大限度减少后期返工。
