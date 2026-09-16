# 前端 ↔ 后端接口映射与契约差异

这份文档回答一个问题：**前端到底能调什么、不能调什么，以及规格文档说错的地方实际是什么。**

规格 §57 定下了处理方式：

> 前端必须严格根据 `docs/API_CONTRACT.md` 调用 API。禁止猜测 API / 字段 / 状态 / 返回结构。
> 如果 API 文档与后端代码不一致：停止当前任务 → 确认真实 API → 更新 API_CONTRACT.md → 继续开发。

本文就是那些「确认真实 API」的落地记录。每条差异都给出后端依据（文件），
前端代码里对应的处理也标明位置，避免后来者重新踩一遍。

---

## 1. 核对方式（事实来源）

| 来源 | 用途 |
| --- | --- |
| `app.openapi()` | 端点清单、路径与操作数（离线可导出，不需要连库） |
| `app/api/v1/*.py` | 每个操作依赖的权限（`require_permission(...)`） |
| `app/schemas/*.py` | 请求体 / 响应体的**真实字段名** |
| `app/core/exceptions.py` | 错误信封与状态码语义 |
| `app/core/middleware.py` | 限流范围、响应头 |
| `docs/API_CONTRACT.md` | 已有契约文档（与实现冲突时以实现为准，并在此记录） |

导出命令（不需要数据库）：

```bash
python -c "from app.main import app; print(len(app.openapi()['paths']))"
```

**当前规模：25 条 `/api/v1` 路径 / 38 个操作**，另有 `GET /` 与 `GET /health` 两个非版本化端点。

---

## 2. 端点总览（含功能级权限）

> 「资源级」列指 Service 层的归属校验：不满足时统一返回 **404**（与「不存在」同文案，防 id 枚举，
> 见 `app/core/exceptions.py::ResourceNotFoundError`）。

| 操作 | 端点 | 功能级权限 | 资源级 |
| --- | --- | --- | --- |
| 注册 | `POST /api/v1/auth/register` | — | — |
| 登录 | `POST /api/v1/auth/login` | — | — |
| 刷新令牌 | `POST /api/v1/auth/refresh` | — | — |
| 登出 | `POST /api/v1/auth/logout` | 需认证 | 只能撤销自己的 Refresh Token |
| 当前用户 | `GET /api/v1/users/me` | 需认证 | — |
| 创建团队 | `POST /api/v1/teams` | `team:create` | — |
| 团队列表 | `GET /api/v1/teams` | `team:read` | 仅我参与的团队 |
| 团队详情 | `GET /api/v1/teams/{team_id}` | `team:read` | 非成员 → 404 |
| 改团队 | `PATCH /api/v1/teams/{team_id}` | `team:update` | **仅 OWNER** |
| 删团队 | `DELETE /api/v1/teams/{team_id}` | `team:delete` | **仅 OWNER** |
| 邀请成员 | `POST /api/v1/teams/{team_id}/members` | `team:invite` | OWNER / ADMIN |
| 成员列表 | `GET /api/v1/teams/{team_id}/members` | `team:read` | 团队成员 |
| 移除成员 | `DELETE /api/v1/teams/{team_id}/members/{user_id}` | `team:invite` | OWNER > ADMIN > MEMBER 层级 |
| 创建项目 | `POST /api/v1/projects` | `project:create` | 团队归属链 |
| 项目列表 | `GET /api/v1/projects` | `project:read` | 我参与的团队的项目 |
| 项目详情 | `GET /api/v1/projects/{project_id}` | `project:read` | 同上，否则 404 |
| 改项目 | `PATCH /api/v1/projects/{project_id}` | `project:update` | 项目所属团队成员 |
| 删项目 | `DELETE /api/v1/projects/{project_id}` | `project:delete` | 同上 |
| 创建任务 | `POST /api/v1/tasks` | `task:create` | 项目所属团队成员 |
| 任务列表 | `GET /api/v1/tasks` | `task:read` | `project_id` **必填** |
| 任务详情 | `GET /api/v1/tasks/{task_id}` | `task:read` | 项目所属团队成员 |
| 改任务 | `PATCH /api/v1/tasks/{task_id}` | `task:update` | 同上 |
| 删任务 | `DELETE /api/v1/tasks/{task_id}` | `task:delete` | 同上 |
| 状态流转 | `POST /api/v1/tasks/{task_id}/transition` | **`task:transition`** | 项目所属团队成员 |
| 添加负责人 | `POST /api/v1/tasks/{task_id}/assignees` | `task:update` | 同上 |
| 移除负责人 | `DELETE /api/v1/tasks/{task_id}/assignees/{user_id}` | `task:update` | 同上 |
| 发表评论 | `POST /api/v1/tasks/{task_id}/comments` | `comment:create` | 任务所属团队成员 |
| 评论列表 | `GET /api/v1/tasks/{task_id}/comments` | `task:read` | 同上 |
| 删评论 | `DELETE /api/v1/comments/{comment_id}` | `comment:delete` | 自己或团队管理者 |
| 上传附件 | `POST /api/v1/tasks/{task_id}/attachments` | `attachment:upload` | 任务所属团队成员 |
| 附件列表 | `GET /api/v1/tasks/{task_id}/attachments` | `task:read` | 同上 |
| 下载附件 | `GET /api/v1/attachments/{attachment_id}` | `attachment:download` | 同上 |
| 删附件 | `DELETE /api/v1/attachments/{attachment_id}` | `attachment:upload` | 同上 |
| 我的日志 | `GET /api/v1/logs` | `log:read` | **仅当前用户自己** |
| 资源日志 | `GET /api/v1/logs/{resource_type}/{resource_id}` | `log:read` | 资源归属链 |
| 通知列表 | `GET /api/v1/notifications` | 需认证 | 仅自己的收件箱 |
| 全部已读 | `PATCH /api/v1/notifications/read-all` | 需认证 | 仅自己的收件箱 |
| 单条已读 | `PATCH /api/v1/notifications/{notification_id}/read` | 需认证 | 非本人 → 404 |

### 两种角色的实际能力差异

种子数据（`migrations/versions/0de65c197efc_seed_rbac_data.py`）里 **admin 拥有全部 22 项权限，
member 只有 10 项**（5 项 read + `task:create` / `task:update` / `comment:create` /
`attachment:upload` / `attachment:download`）。

因此**普通成员（member）会 403 的操作**：建/改/删团队、邀请成员、建/改/删项目、
删任务、分配负责人、**状态流转**、删评论。

前端必须知道的后果：一个 member 用户在界面上看到「改状态」按钮并点击会拿到
`403 {"detail": "Permission denied: task:transition"}`。在拿不到权限集合的前提下
（见 §4-D4），前端无法提前隐藏它——所以任务状态相关的 UI 必须对该 403 有明确提示，
而不是静默失败。

---

## 3. 页面 ↔ 端点映射

| 页面（路由） | 端点 | 备注 |
| --- | --- | --- |
| 登录 `/login` | `POST /auth/login` → `GET /users/me` | 登录响应只有令牌，用户资料需另拉一次 |
| 注册 `/register` | `POST /auth/register` | 201 返回 `UserRead` |
| 首页 `/dashboard` | `GET /teams`、`GET /projects`、`GET /notifications`、`GET /logs` | 任务统计缺跨项目端点，见 §4-D8 |
| 我的任务 `/tasks` | `GET /tasks?project_id=…` | `project_id` 必填，见 §4-D7 |
| 任务看板 `/tasks/board` | `GET /tasks?project_id=…&status=…`、`POST /tasks/{id}/transition` | 拖拽换列必须走 transition |
| 任务详情 `/tasks/:taskId` | `GET/PATCH/DELETE /tasks/{id}`、`/transition`、`/assignees`、`/comments`、`/attachments`、`GET /logs/task/{id}` | 跨阶段页面 |
| 项目列表 `/projects` | `POST /projects`、`GET /projects` | |
| 项目详情 `/projects/:projectId` | `GET /projects/{id}`、`GET /tasks?project_id={id}` | 任务列表的天然入口 |
| 项目设置 `/projects/:projectId/settings` | `PATCH/DELETE /projects/{id}` | 删除需二次确认 |
| 团队列表 `/teams` | `POST /teams`、`GET /teams`、`DELETE /teams/{id}` | |
| 团队详情 `/teams/:teamId` | `GET/PATCH /teams/{id}` | 非 OWNER 改 → 404 |
| 成员管理 `/teams/:teamId/members` | `GET/POST /teams/{id}/members`、`DELETE …/{user_id}` | 按 `user_id` 邀请 |
| 通知 `/notifications` | `GET /notifications`、`PATCH /read-all`、`PATCH /{id}/read` | 无未读筛选 |
| 操作日志 `/logs` | `GET /logs`、`GET /logs/{type}/{id}` | 前者只含自己 |
| 个人中心 `/profile` | `GET /users/me` | 无可用的资料更新端点，见 §4-D12 |
| 顶部铃铛（布局） | `GET /notifications?limit=5` | 未读数前端统计，见 §4-D9 |

---

## 4. 契约差异（逐条）

编号 `D#` 与 `docs/QUALITY.md` 的缺陷编号无关，仅本文内部引用。

### D1 · 响应信封没有 `code`

- **规格 §40 说法**：`{"code": 0, "message": "success", "data": {}}`，前端统一判 `response.code`。
- **后端事实**：`app/schemas/common.py::SuccessResponse` 只有 `data` + `message`（默认 `"success"`）。
  错误响应是 `{"detail": ...}`（`app/core/exceptions.py::app_error_handler`），**也没有 code**。
- **前端处理**：`src/types/common.ts` 按真实信封定义 `ApiEnvelope<T>`；`src/utils/request.ts`
  在响应拦截器里直接解包 `data`，业务代码拿不到也不需要 `code`。错误靠 HTTP 状态码判定。
  规格 §40 那句「不要每个页面重复 `if response.code...`」的目标仍然达到——只是判据换成了状态码。

### D2 · 当前用户端点不是 `/auth/me`

- **规格 §58 说法**：`当前用户 → /auth/me`。
- **后端事实**：`GET /api/v1/users/me`（`app/api/v1/users.py`，router prefix 是 `/users`）。
  `app/api/v1/auth.py` 下只有 register / login / refresh / logout 四个端点。
- **前端处理**：`src/api/auth.ts::fetchCurrentUser` 用 `/users/me`，并在注释里写明这处偏差。

### D3 · 分页是 `skip` / `limit`，且响应没有总数

- **规格 §46 说法**：`page` / `pageSize`。
- **后端事实**：所有列表端点（`GET /tasks`、`GET /notifications`、`GET /logs`）
  只有 `skip`（offset，`ge=0`）与 `limit`（page size，`1..100`），响应是**裸数组**，
  既没有 `total` 也没有 `page`/`pages`。
- **后果**：前端**无法**算出总页数，规格 §46 的完整分页器（跳页、总条数）在此契约下不可实现。
  可行形态是「上一页 / 下一页 + 当前是否还有下一页（取满 limit 即认为可能有）」。
- **前端处理**：`src/types/common.ts::PaginationParams` 只声明 `skip`/`limit`；
  分页组件（阶段 8 交付）按上面的可行形态实现。`docs/DECISIONS.md` 044 已就此订正过文档口径。

### D4 · 没有权限查询端点 → 前端拿不到权限集合

- **规格 §34 说法**：列出 `user:read`、`team:create`、`task:update` 等权限，§35 给出
  `<el-button v-if="hasPermission('task:update')">` 的用法。
- **后端事实**：`docs/API_CONTRACT.md` 明确「授权机制（TASK-023 / TASK-024，**内部机制，无独立端点**）」；
  `GET /users/me` 返回的 `UserRead` 只有 `id/username/email/is_active/created_at/updated_at`，
  **没有角色字段，也没有权限字段**。
- **前端处理**：`src/composables/usePermission.ts` 保留落点，但集合恒为空，
  并且**不据此隐藏任何功能**。理由：规格 §35 自己写着「隐藏按钮 ≠ 安全」，
  真正裁决权限的是后端；在没有事实的情况下凭空造一份权限表，会让开发者误以为前端已经守住了权限
  （比不做更危险）。替代方案见 §6-Q1。

### D5 · 资源级无权限表现为 404，不是 403

- **规格 §36 / §41 说法**：无权限 → `/403`。
- **后端事实**：功能级权限缺失 → `403`；**资源级**归属不满足（团队/项目/任务不在我的归属链上）
  → `404`，与「资源不存在」**同文案**（`ResourceNotFoundError`，刻意防 id 枚举）。
- **前端处理**：页面按「404 = 数据不存在」处理即可；403 才跳 `/403`。
  详情页尤其要注意：拿不到数据时不要断言「被删了」，也可能只是没有归属权。

### D6 · 团队邀请按 `user_id`，不是邮箱

- **规格 §15 说法**：团队邀请（未明确标识类型）。
- **后端事实**：`POST /teams/{team_id}/members` 请求体 `{user_id, role}`，
  `role` 只接受 `admin` / `member`（`"owner"` → 422）；目标用户不存在 → 404。
  成员列表返回的 `role` 是小写名 `owner|admin|member`。
- **前端处理**：邀请表单按 `user_id` 设计；`role` 用下拉（两项），不做「输入邮箱邀请」。

### D7 · `GET /tasks` 的 `project_id` 必填

- **规格 §20 说法**：任务列表 + 搜索 + 筛选 + 排序（未提 project_id 约束）。
- **后端事实**：`project_id: Annotated[int, Query(...)]` **无默认值**（`app/api/v1/tasks.py`），
  不传 → 422。其他参数（`status`、`priority`、`keyword`、`assignee_id`、`sort`、`order`）都是可选的，
  也就是说**后端能力比规格假设的更强**——除了这个必填项。
- **后果**：规格 §5 的「我的任务」不能是一个跨项目的全局页面。
- **前端处理**：`/tasks` 做成项目上下文驱动的页面（或在选定项目后加载）；
  占位页把这个约束写在界面上（`src/views/task/TaskList.vue`），不让后来者以为是漏做。
  `assignee_id` 用来表达「我的任务」，不用独立端点。

### D8 · 没有跨项目的任务统计端点

- **规格 §11.2 说法**：首页展示任务统计。
- **后端事实**：任务只能按 `project_id` 查，没有聚合/统计端点。
- **前端处理**：Dashboard 的任务统计需要先决定方案（逐项目拉取后合并，或后端补统计端点），
  已在占位页写明。**不为它编造接口**。

### D9 · 没有「未读数」与「未读筛选」

- **规格 §31 说法**：顶部消息通知显示未读。
- **后端事实**：`GET /notifications` 返回完整列表项（含 `is_read`），没有 unread-count 端点，
  也没有 `is_read` 查询参数。`limit` 上限 100。
- **前端处理**：`src/stores/notification.ts` 在已取回的列表上统计未读数。
  **已知偏差**：通知超过 100 条时角标会偏小。这是后端契约的限制，不是前端 bug。

### D10 · 登出需要认证头 + 请求体里的 Refresh Token

- **规格 §10 说法**：清除认证信息 → 跳 `/login`。
- **后端事实**：`POST /auth/logout` 依赖 `CurrentUser`（**需要有效 Access Token**），
  且请求体是 `{refresh_token}`。撤销是**幂等**的：Token 本来就不可用时静默成功，
  只有出示**他人**的 Refresh Token 才 403。
- **前端处理**：`stores/auth.ts::logout` 先请求撤销再清本地状态，并把撤销失败也当作成功
  （后端语义允许），保证「点了登出就登出」。Refresh Token 从 `tokenStorage` **现取**
  而不是从 ref 读——刷新轮换后 ref 会是旧值，用它撤销等于撤销了一个已经失效的令牌，
  真正有效的那一个反而活了下来。
- **遗留**（见 `docs/DECISIONS.md` 014）：Access Token 本身不可撤销，登出后最长
  `access_token_expire_minutes`（30 分钟）内仍会被后端接受。前端无法弥补，只能如实记录。

### D11 · 状态流转必须走 `transition`，且只有 admin 有权限

- **规格 §24 说法**：任务状态流转。
- **后端事实**：`POST /tasks/{task_id}/transition` 由**状态机**裁决合法转移
  （`app/services/state_machine.py`），非法转移被拒绝；功能级权限是独立的
  `task:transition`，**种子只有 admin 持有，member 会 403**。
- **前端处理**：看板拖拽/下拉改状态只能调 transition，不能 `PATCH status`；
  必须处理 member 的 403 提示。

### D12 · 没有更新资料 / 改密端点

- **规格 §33 说法**：个人中心含「修改个人信息」「修改密码」。
- **后端事实**：`app/api/v1/users.py` 只有 `GET /users/me`；全仓没有 `PATCH /users/me`、
  没有改密端点。`permissions` 里也没有对应的写权限。
- **前端处理**：`src/views/profile/Profile.vue` 展示资料 + 退出登录，
  「修改资料 / 修改密码」按钮**禁用**并注明原因（说明为什么不做界面：规格 §57 禁止猜 API）。

### D13 · 附件上传的字段名与校验口径

- **规格 §53 说法**：前端可检查大小 / 扩展名 / MIME，但不能替代后端。
- **后端事实**：`multipart/form-data`，文件字段名固定为 **`file`**；
  `Content-Type` 由客户端自报但**不采信**，后端一律**按扩展名**判定类型；
  大小上限 `max_upload_size = 10485760`（10 MiB，`app/core/config.py`）；
  文件名经 `sanitize_filename` 清洗，存储键由服务端生成（不使用客户端文件名做路径）。
- **前端处理**：阶段 10 实现上传时用字段名 `file`、`FormData` 不要手写 `Content-Type`；
  前端可预检大小/扩展名以便即时反馈，但必须按后端可能拒绝来写错误分支。

### D14 · 限流是全局的，且按「用户优先、否则 IP」

- **规格 §22 说法**：Redis 滑动窗口限流。
- **后端事实**：中间件对 **所有** `/api/v1` 路径生效（`RATE_LIMITED_PREFIX`），
  默认 `60 请求 / 60 秒`（`rate_limit_requests` / `rate_limit_window_seconds`）。
  **带 Bearer 时按 user_id 计数，否则按客户端 IP**（`_rate_limit_identity`）。
  超限返回 `429`，带 `Retry-After`、`X-RateLimit-Limit`、`X-RateLimit-Remaining` 响应头。
- **前端处理**：`src/utils/request.ts` 把 429 映射为「请求过于频繁，请稍后再试」。
  注意**登录端点也在限流域内**——连续输错密码会把整个 IP 的配额打满，
  因此「登录失败自动重试」这类逻辑是错的，不能加。

---

## 5. 前端因此形成的实现约定

1. **只有 `src/api/*` 允许出现 URL 字符串**，页面通过 `xxxApi.yyy()` 调用（规格 §37/§38）。
2. **字段名保持后端的 snake_case**，不做驼峰转换——转换代码漏一个字段就是静默 bug。
3. **不猜枚举值**：任务状态/优先级等枚举来自 `app/models/task.py` 与 OpenAPI schema。
4. **错误处理统一在请求层**（`ApiError{status, message, detail}`），页面只处理
   「需要额外反应」的分支（401 已由拦截器接管、404 走空状态、403 跳 `/403`）。
5. **`silent: true` 用于非阻断请求**（通知铃铛预览等），避免布局级请求失败时反复弹窗。

---

## 6. 需要后端配合的未决项

| 编号 | 事项 | 影响 | 建议 |
| --- | --- | --- | --- |
| Q1 | 缺「我的权限集合」查询端点 | 前端无法按权限隐藏入口，member 会看到自己点不动的按钮（`task:transition` 最明显） | 后端加 `GET /users/me/permissions`（或让 `UserRead` 带 `permissions`） |
| Q2 | 缺跨项目的任务统计/查询 | 首页统计与「我的任务」都无法做成全局视图 | 后端加统计端点，或放开 `project_id` 为可选 |
| Q3 | 列表无 `total` | 分页器无法显示总条数与跳页 | 列表端点补 `total`（可选启用 `X-Total-Count` 头，注意别影响既有响应体契约） |
| Q4 | 缺更新资料 / 改密端点 | 个人中心的两项功能无法实现 | 明确是否纳入范围，避免前端长期挂着两个禁用按钮 |

这四项都**不阻塞**已交付的前端阶段（1-3），但会阻塞后续业务页面的一部分功能。
在前端阶段 4 及之后遇到它们时，按 §57 的流程处理：停下来、确认、记录、再继续。

---

## 7. 当前占位页清单

以下页面目前是占位实现（写明阶段与将调用的端点），不是漏做：

| 页面 | 计划阶段 | 阻塞点 |
| --- | --- | --- |
| 首页 Dashboard | 阶段 5 | 已实现（团队/项目/通知/日志概览，TASK-069）；任务统计与全局「最近任务」仍受 Q2/D7 阻塞，页面已注明，不编造接口 |
| 团队列表 / 详情 / 成员管理 | 阶段 6 | — | **已实现（TASK-070）**：列表+创建+删除、详情（基本信息/项目/编辑设置）、成员邀请（user_id）/移除均接真实端点；「任务统计」与「邮箱列」「改角色」按 §4-D6/D8 降级并在页面明示 |
| 项目列表 / 详情 / 设置 | 阶段 7 | — | **已实现（TASK-071）**：列表卡片+客户端搜索/团队筛选（`GET /projects` 无搜索与 total）、创建按 team_id（`GET /teams` 选团队）、详情四标签（任务列表/看板=阶段8占位、项目成员=复用 `GET /teams/{team_id}/members`、项目设置跳转）、设置页 `PATCH`/`DELETE`；ProjectRead 无 status 与成员/任务/进度字段，「成员：N/任务：N/78%/状态筛选」按诚实降级顶部提示、不编造接口 |
| 我的任务 / 看板 / 详情 / 新建 | 阶段 8 | — | **已实现（TASK-072）**：列表表格+客户端搜索/优先级/状态筛选/排序/分页、看板 HTML5 拖拽走 `POST /tasks/{id}/transition`（状态机白名单仅前端提示，真实以后端为准，member 无 `task:transition` 权限时 403 由请求层提示）、详情含 transition 下拉/编辑抽屉/分配成员(`GET /teams/{team_id}/members`)/删除、创建后 `POST /tasks/{id}/assignees` 指派；跨项目「我的任务」全局视图仍受 D7/D8·Q2 阻塞，页面用「项目选择器 + assignee_id=当前用户」诚实表达并顶部提示、不编造接口 |
| 评论（任务详情内） | 阶段 9 | — | **已实现（TASK-073）**：任务详情内评论区块接 `GET/POST /tasks/{task_id}/comments`、`DELETE /comments/{comment_id}`；`CommentRead` 内嵌 `username` 直接渲染作者名、textarea 限 2000 字；删除按钮按 `comment.user_id === 当前用户` 数据驱动显示（规格 §28「删除自己的评论」）；**功能级 `comment:delete` 种子仅 admin 持有且先于资源级判定执行，普通成员删自己的评论也会 403**（§4-D11），由请求层提示、前端不臆测权限集隐藏按钮（见 DECISIONS 052） |
| 附件（任务详情内） | 阶段 10 | D13（上传字段与校验口径） |
| 通知列表 | 阶段 11 | D9（无未读筛选） |
| 操作日志 | 阶段 13 | — |

已完成并接真实后端的页面：**登录、注册、个人中心（只读部分）**，以及主框架的
导航、面包屑、用户菜单与通知铃铛。
