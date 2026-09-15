# API Contract

> 本文件只登记项目开发文档中已经明确的 API。后续新增 API 必须同步更新本文件。

## 基础路径
`/api/v1`

## Auth
- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

## 授权机制（TASK-023 / TASK-024，内部机制，无独立端点）
后续资源端点通过权限依赖 `require_permission("resource:action", ...)` 声明所需权限（多值 AND 语义）：

- 未认证（无/非法 Token）→ `401` + `WWW-Authenticate: Bearer`（与 `/users/me` 一致）。
- 已认证但账号禁用 → `403` `{"detail": "User account is disabled"}`。
- 已认证但缺少所需权限 → `403` `{"detail": "Permission denied: <缺失的权限名, 逗号分隔>"}`（多权限 AND 时只列出缺失项）。
- 权限名严格 `resource:action` 格式（§6），用户有效权限 = 其全部角色的权限并集（去重）。
- 种子角色（TASK-022）：`admin` 持有全部 22 项权限；`member` 持有 10 项「读 + 基础写」。

**资源级权限（TASK-024）**：功能级判定（上面 403 一条）之外，业务层（Service）还需资源归属校验——开发文档 §49 的 `User → Team → Project → Task` 归属链，防止 IDOR：

- **资源不存在** 与 **资源存在但不在调用者归属链上**（如跨团队访问他人任务）→ 统一 `404` `{"detail": "<资源> not found"}`（`ResourceNotFoundError`）。TASK-024 决策：两种情形不可区分，防止通过 403/404 差异枚举资源 id。
- 功能级权限缺失（不针对具体资源）仍是 `403`（`require_permission` 依赖 / `ensure_permission` 守卫，两者语义与文案一致）；404 与 403 不得混用。
- `ensure_permission`（`app/services/authorization.py`）是依赖的 Service 层等价物：Service 互调、后台任务等无 HTTP 上下文场景使用，语义（单权限/AND）与报错文案完全一致。

### POST `/api/v1/auth/register`（TASK-015 已实现）

Request：

```json
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "S3cret-Passw0rd!"
}
```

Response `201 Created`：

```json
{
  "data": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "is_active": true,
    "created_at": "2026-09-13T12:00:00Z",
    "updated_at": "2026-09-13T12:00:00Z"
  },
  "message": "success"
}
```

- `data` 永不包含 `password` 或 `password_hash`。
- 用户名或邮箱已存在 → `409 Conflict`：`{"detail": "..."}`。
- 缺少必填字段 → `422 Unprocessable Entity`。

### POST `/api/v1/auth/login`（TASK-016 已实现，TASK-018 扩展为双 Token）

Request：

```json
{
  "username": "alice",
  "password": "S3cret-Passw0rd!"
}
```

`username` 为账号标识（对应 `users.username` 列）。

Response `200 OK`：

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  },
  "message": "success"
}
```

- `access_token` 为 HS256 签名的 JWT，claims：`sub`（用户 id，字符串）、`type`（`"access"`）、`iat`、`exp`（默认 30 分钟后过期，由 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制）。
- `refresh_token` 同样为 HS256 JWT，claims：`sub`、`type`（`"refresh"`）、`jti`（UUID4，唯一标识）、`iat`、`exp`（默认 7 天后过期，由 `REFRESH_TOKEN_EXPIRE_DAYS` 控制）。
- 登录时**只有 `refresh_token` 的 `jti` 与 `expires_at` 落库**（`refresh_tokens` 表），Token 本体不持久化（开发文档 §55.1）。
- 客户端使用方式：`Authorization: Bearer <access_token>`。
- 用户名不存在或密码错误 → `401 Unauthorized`：`{"detail": "Invalid username or password"}`（两种情形文案一致，避免用户名枚举），响应头含 `WWW-Authenticate: Bearer`。
- 密码正确但账号被禁用（`is_active=false`）→ `403 Forbidden`：`{"detail": "User account is disabled"}`。
- 缺少必填字段 → `422 Unprocessable Entity`。
- 响应永不包含 `password` 或 `password_hash`。

### POST `/api/v1/auth/refresh`（TASK-018 已实现）

Request：

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

Refresh Token 通过请求体传递（项目无 Cookie/Session 机制，凭证一律走显式字段）。

Response `200 OK`：结构同 login，返回**全新的 Token 对**。

```json
{
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer"
  },
  "message": "success"
}
```

- **采用轮换策略**：每次 refresh 都签发新的 Refresh Token，并把旧 `jti` 立即置 `revoked=true`；旧 Refresh Token 之后再次使用一律 `401`（可用于识别 Token 被复制使用）。
- Refresh Token 的 claims 含唯一 `jti`，故新旧 `refresh_token` 必然不同；`access_token` 的 claims 只精确到秒，同一秒内签发可能得到完全相同的串——客户端应以响应中的值为准，不要假定它一定变化。
- 校验顺序：签名/过期/`type` → jti 是否登记在库（§19「检查数据库 JTI」）→ 是否已撤销 → 库中 `expires_at` 是否过期 → 账号是否存在/是否启用。
- 任一 Token 校验失败（签名错误、已过期、`type` 不是 `refresh`、jti 未知、jti 已撤销、库中已过期、`sub` 非法）→ `401 Unauthorized`：`{"detail": "..."}`，文案不区分具体原因。
- Token 有效但账号已被禁用 → `403 Forbidden`：`{"detail": "User account is disabled"}`（与 `/users/me` 一致）。
- 刷新失败时**不产生**新的 `refresh_tokens` 记录，也不改动已有记录。
- 缺少必填字段 → `422 Unprocessable Entity`。
- 登出与主动撤销（`POST /api/v1/auth/logout`）见下节（TASK-019）。

### POST `/api/v1/auth/logout`（TASK-019 已实现）

认证：必须携带请求头 `Authorization: Bearer <access_token>`（与 `/users/me` 同一套认证规则）。

Request：

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

Response `200 OK`：

```json
{
  "data": null,
  "message": "success"
}
```

- 语义（开发文档 §19「登出：撤销 Refresh Token」）：把请求体中 Refresh Token 的 `jti` 置 `revoked=true`；之后该 Token 用于 `/auth/refresh` 一律 `401`。
- **幂等**（TASK-019 决策）：登出的目标是「让这个 Refresh Token 不可用」，因此签名/过期/类别不合法、`jti` 未登记、`jti` 已撤销等「Token 本来就不可用」的情形一律返回 `200`（无副作用），客户端可无条件清理本地凭证。
- **归属校验**：出示的 Refresh Token 有效但属于其他用户 → `403 Forbidden`：`{"detail": "Refresh token does not belong to current user"}`，且**不产生**任何撤销动作（防越权撤销他人凭证，项目规则 §9 IDOR）。
- Access Token 认证失败（缺头/非 Bearer/签名错误/已过期/`type` 不是 `access`/用户不存在）→ `401 Unauthorized`，带 `WWW-Authenticate: Bearer`；账号禁用 → `403`（与 `/users/me` 一致），两种情况下 Refresh Token 均不会被改动。
- 缺少 `refresh_token` 字段 → `422 Unprocessable Entity`。
- 本阶段**不引入** Redis JWT 黑名单（开发文档 §19「必要时支持」）：Access Token 30 分钟短时效 + Refresh 轮换已可控风险；登出后旧 Access Token 在剩余有效期内仍可访问资源，属已知且接受的行为。

## User
- GET `/api/v1/users/me`

### GET `/api/v1/users/me`（TASK-017 已实现）

认证：必须携带请求头 `Authorization: Bearer <access_token>`，Token 由 `POST /api/v1/auth/login` 签发。

Response `200 OK`：

```json
{
  "data": {
    "id": 1,
    "username": "alice",
    "email": "alice@example.com",
    "is_active": true,
    "created_at": "2026-09-13T12:00:00Z",
    "updated_at": "2026-09-13T12:00:00Z"
  },
  "message": "success"
}
```

- 返回当前 Token 所属用户的资料，字段与 `POST /api/v1/auth/register` 的 `data` 完全一致（`UserRead`）。
- 响应永不包含 `password` 或 `password_hash`。
- 缺少 `Authorization` 头、方案不是 `Bearer`、Token 签名错误/已过期/`type` 不为 `access`、或 `sub` 无法解析为合法用户 id → `401 Unauthorized`：`{"detail": "..."}`，响应头含 `WWW-Authenticate: Bearer`。
- Token 签名有效但对应账号已不存在 → 同样 `401`，且文案与上一条不作区分（避免探测账号是否存在）。
- Token 有效、账号存在但 `is_active=false`（已被禁用）→ `403 Forbidden`：`{"detail": "User account is disabled"}`。与 `POST /api/v1/auth/login` 对禁用账号的处理保持同一语义。
- 本接口只读，不修改任何数据。

## Team（TASK-027 已实现：团队 CRUD；TASK-028 已实现：成员管理）

授权两层（与全局契约一致）：功能级权限缺失 → `403`（`require_permission` 依赖）；资源级归属不满足 → `404` `{"detail": "Team not found"}`（`ResourceNotFoundError`，与「不存在」不可区分，防 id 枚举）。

**TASK-027 决策**：
1. 创建团队时自动在 `team_members` 写入一条 `OWNER` 行（`role_id=1`），成员归属链统一以 `team_members` 为准。
2. `PATCH` / `DELETE` 资源级**仅 owner**（`teams.owner_id == 当前用户`）；有功能权限但非 owner → 404。
3. `GET` 列表/详情的可见范围 = **我参与的团队**（owner 或 `team_members` 成员）。

### POST `/api/v1/teams`

Request：

```json
{
  "name": "Platform Team",
  "description": "平台研发团队"
}
```

- `name` 必填（1–150 字符）；`description` 可选（≤255 字符）。
- Response `201 Created`：`{"data": {"id", "name", "description", "owner_id", "created_at", "updated_at"}, "message": "success"}`，`data` 为 `TeamRead`。
- 需要功能权限 `team:create`；创建者成为 owner（`teams.owner_id` + `team_members` OWNER 行）。
- 校验失败（空/超长 name、超长 description）→ `422`；缺权限 → `403 Permission denied: team:create`；未认证 → `401`。

### GET `/api/v1/teams`

- Response `200`：`{"data": [TeamRead...], "message": "success"}`——按 `id` 升序，仅含当前用户参与的团队。
- 分页查询参数：`skip`（默认 0，≥0）、`limit`（默认 100，1–100）。
- 需要功能权限 `team:read`。

### GET `/api/v1/teams/{team_id}`

- Response `200`：`{"data": TeamRead, "message": "success"}`。
- 可见性：owner 或团队成员；他人团队与不存在的团队统一 `404 {"detail": "Team not found"}`。
- 需要功能权限 `team:read`。

### PATCH `/api/v1/teams/{team_id}`

Request（部分更新，仅应用显式出现的字段；`description` 显式传 `null` 表示清空）：

```json
{"description": "新描述"}
```

- Response `200`：`{"data": TeamRead, "message": "success"}`。
- 需要功能权限 `team:update`；资源级**仅 owner**，非 owner → `404`（即使存在）。
- `name` 传 `null`/空串/超 150 字符 → `422`。

### DELETE `/api/v1/teams/{team_id}`

- Response `200`：`{"data": null, "message": "success"}`。
- 需要功能权限 `team:delete`；资源级**仅 owner**，非 owner → `404`。
- 删除团队时 `team_members` 行随 ON DELETE CASCADE 级联清理。

## Team Members（TASK-028 已实现）

**TASK-028 决策**：
1. **双层判定**：功能级 `team:invite`（邀请/移除）或 `team:read`（列表）+ 资源级**团队角色** OWNER/ADMIN（列表仅需团队成员可见）。全局权限缺失 → 403（先行）；团队角色不足 → 403 `Only team owner or admin can manage members`；团队不在归属链 → 404（与团队 CRUD 一致）。
2. **邀请请求体** `{user_id, role}`：`role` 仅接受 `admin` / `member`（默认 `member`），`"owner"` → 422——owner 不可被邀请（只能经创建/转让获得）。
3. **移除层级 OWNER > ADMIN > MEMBER**：owner 可移除任何非 owner 成员；admin 仅可移除 member；owner 不可被移除（403，含 owner 自移）——与 `teams.owner_id` RESTRICT 语义一致，退出只能经转让（后续 TASK）。

### POST `/api/v1/teams/{team_id}/members`

Request：

```json
{"user_id": 42, "role": "admin"}
```

- 需要功能权限 `team:invite` + 团队角色 OWNER/ADMIN。
- Response `201 Created`：`{"data": {"id", "team_id", "user_id", "username", "role", "joined_at"}, "message": "success"}`（`role` 为小写名 `owner|admin|member`）。
- 目标用户不存在 → `404 {"detail": "User not found"}`；已是成员 → `409 {"detail": "User is already a team member"}`；团队不可见 → `404 {"detail": "Team not found"}`。

### GET `/api/v1/teams/{team_id}/members`

- 需要功能权限 `team:read`；团队成员（owner 或成员）可见，局外人 → `404 {"detail": "Team not found"}`。
- Response `200`：`{"data": [成员...], "message": "success"}`，按入队时间（`joined_at`）升序，owner 最先。

### DELETE `/api/v1/teams/{team_id}/members/{user_id}`

- 需要功能权限 `team:invite` + 团队角色 OWNER/ADMIN；移除层级见决策 3。
- Response `200`：`{"data": null, "message": "success"}`。
- 目标不是成员 → `404 {"detail": "Team member not found"}`；移除 owner / ADMIN 移除非 MEMBER → `403 {"detail": "Team owner cannot be removed"}` / `{"detail": "Team admin can only remove members"}`。
- 被移除者即刻失去该团队可见性（`GET /teams/{id}` → 404）。

## Project（TASK-029 已实现：项目 CRUD）
- POST `/api/v1/projects` → 201。功能级 `project:create`（403）；资源级：**团队成员即可创建**（决策 2），团队不存在或调用者非成员 → 404（同一文案，IDOR 防枚举）。请求体 `{team_id, name, description?}`；`owner_id` 恒为当前调用者，不开放客户端指定。
- GET `/api/v1/projects` → 我所在团队（`team_members` 有行）下的全部项目（决策 4），skip/limit 分页（skip≥0，limit 1-100 默认 100），按 id 升序。需 `project:read`。
- GET `/api/v1/projects/{project_id}` → 项目所属团队成员可见（规格 §5「所属团队链路」）；不存在或不在归属链 → 404 `Project not found`。需 `project:read`。
- PATCH `/api/v1/projects/{project_id}` → 功能级 `project:update`（403）+ 资源级**团队角色 OWNER/ADMIN**（决策 3；角色不足 → 403 `Only team owner or admin can manage projects`，不在归属链 → 404）。请求体 `{name?, description?}`，exclude_unset 部分更新：`description` 显式传 null 清空，未传不变。
- DELETE `/api/v1/projects/{project_id}` → 功能级 `project:delete` + 团队角色 OWNER/ADMIN。200 后复查 404。删团队时项目随 `team_id` CASCADE 级联清理。

## Task
> **TASK-034 已实现：五端点挂载完成。** 授权两层（TASK-032/033 决策）：授权两层：功能级（task:create/read/update/delete）+ 资源级（本注，IDOR 契约：不在归属链一律 404 同文案；调用者已在归属链上时明示 403）——创建/更新 = 项目所属团队成员即可（task:create/task:update + team_members 有行）；删除 = 团队角色 OWNER/ADMIN（403 文案 `Only team owner or admin can delete tasks`，与种子设计对齐：member 全局角色有 task:update 无 task:delete）；创建时项目不存在或非成员统一 404 `Project not found`（类比 POST /projects 对不可见团队报 `Team not found`）。TASK-032 Schema 决策：POST 创建请求体**不含 `status`**——新任务一律 TODO 起步，状态流转只能走 transition API（TASK-038），杜绝绕过状态机直接建出非 TODO 任务（Decision 005）；PATCH 请求体同样不含 status / project_id / creator_id。title 1-200，priority 枚举 LOW/MEDIUM/HIGH/URGENT（默认 MEDIUM），due_at 可空。
- POST `/api/v1/tasks`
- GET `/api/v1/tasks?project_id={id}` → **TASK-035 已实现：多条件过滤 + 分页 + 排序**（响应仍为纯列表 `{data: [TaskRead...]}`）。`project_id` 必填（缺失 422）；过滤：`status`（枚举精确，非法 422）、`priority`（枚举精确）、`keyword`（标题大小写不敏感子串 ILIKE，`%`/`_`/`\` 转义后按字面匹配，纯空白视为未传）；分页：`skip`（默认 0，≥0）、`limit`（默认 100，1-100）；排序：`sort` 白名单 `id|created_at|due_at|priority`（默认 id）+ `order` `asc|desc`（默认 asc），**priority 按业务权重（URGENT > HIGH > MEDIUM > LOW）而非字母序**。项目不存在或不在归属链 404 `Task not found`。需 `task:read`。
- GET `/api/v1/tasks/{task_id}` → **TASK-036 起响应内嵌 `assignees: [{user_id, username, assigned_at}]`**（升序，未分配恒空列表）；其余契约不变。
- PATCH `/api/v1/tasks/{task_id}` → 响应同样内嵌 `assignees`。
- DELETE `/api/v1/tasks/{task_id}`
- **TASK-036 已实现：分配/移除负责人（用户确认决策）**——功能级 `task:update`（分配是更新行为，不新增 seed 权限项）+ 资源级**任务所属团队成员即可**（协作式，member 可分配他人与自领）：
  - POST `/api/v1/tasks/{task_id}/assignees` → 201 `{data: {user_id, username, assigned_at}}`；请求体 `{user_id}`。目标用户不存在**或**不是任务所属团队成员 → 404 `User not found`（同文案防枚举）；目标已是负责人 → 409 `User already assigned to this task`；任务不在归属链 → 404 `Task not found`；无全局权限 → 403 `Permission denied: task:update`。`assigned_by` = 调用者（表内 `assigned_by_id`，最小审计）。
  - DELETE `/api/v1/tasks/{task_id}/assignees/{user_id}` → 200 `{data: null}`；授权同分配；目标非该任务负责人 → 404 `Assignee not found`。
  - GET `/api/v1/tasks` 增可选 `assignee_id` query 参数（负责人精确筛选，TASK-035 过滤家族扩展）；TaskRead 全端点（创建/详情/列表/更新）统一内嵌 `assignees`，删除任务时分配行随 FK CASCADE 清理。
- POST `/api/v1/tasks/{task_id}/transition` → **TASK-038 已实现**（流转规则 = TASK-037 状态机，用户确认）：仅严格前进 TODO→IN_PROGRESS→REVIEW→DONE + 非终态（TODO/IN_PROGRESS/REVIEW）→CANCELLED；**终态完全封死**（DONE/CANCELLED 无任何出边，含 →CANCELLED）；相邻回退（IN_PROGRESS→TODO、REVIEW→IN_PROGRESS）与跨级跳转非法。规则落位 `app/services/state_machine.py`（TRANSITIONS / can_transition / validate_transition / allowed_targets），status 仍不允许经普通 PATCH 修改（Decision 005）。
  - **请求体**（TASK-038 决策，用户确认）：`{"to_status": "IN_PROGRESS"}`——`to_status` 必须为五个合法状态之一，非法值 / 缺失 / null → `422`。
  - 授权：功能级 `task:transition`（§6 权限清单专门项，种子仅 admin 持有，member → `403 Permission denied: task:transition`）+ 资源级**任务所属团队成员即可**（协作式，与更新/分配同语义，区别于删除的 OWNER/ADMIN）；任务不在归属链或不存在 → `404 {"detail": "Task not found"}`（同文案，IDOR 防枚举）。
  - Response `200 OK`：`{"data": TaskRead, "message": "success"}`——更新后的任务（含 assignees 内嵌）。
  - 非法流转（相邻回退 / 跨级跳转 / 终态任何出边 / 同状态重复流转）→ `409 Conflict`：`{"detail": "Invalid status transition"}`，任务状态不被改动。
- POST `/api/v1/tasks/{task_id}/assignees`
- DELETE `/api/v1/tasks/{task_id}/assignees/{user_id}`

## Comment
- POST `/api/v1/tasks/{task_id}/comments`（TASK-041）—— 发表评论。功能级 `comment:create`（admin/member 均持有）+ 资源级归属链（Service 校验，非成员/任务不存在 → 404 `Task not found` 防枚举）；请求体 `{content: str}`（1-2000，越界/缺失 → 422）；201 返回 `CommentRead`（`id/task_id/user_id/username/content/created_at/updated_at`）。§16 规则 1/2：须有任务访问权且评论属于任务。
- GET `/api/v1/tasks/{task_id}/comments`（TASK-041）—— 评论列表。**功能级复用 `task:read`**（§6 权限清单无 comment:read，评论是任务一部分）+ 资源级归属链；`created_at` 升序（讨论时间线），分页 `skip`/`limit`（`le=100`）；响应 `list[CommentRead]`。
- DELETE `/api/v1/comments/{comment_id}`（TASK-041）—— 删除评论。功能级 `comment:delete`（种子仅 admin）+ 资源级 **评论作者本人或任务所属团队 OWNER/ADMIN**（两者都不是 → 403 `Only team owner or admin or the comment author can delete comments`）；评论不存在/所属任务不在归属链 → 404 `Comment not found`（同文案防枚举）；**删除写 OperationLog**（§16 规则 4，`action=comment:delete`、`payload={task_id, comment_id}`，与删除同事务）。

## Attachment
（TASK-042 已实现；上传要求见开发文档 §17，端点为 §25.7。注：另有一个删除端点，
支撑 §17「删除需权限 + 清理物理文件」）

- POST `/api/v1/tasks/{task_id}/attachments`（TASK-042）—— 上传附件。功能级 `attachment:upload`（admin/member 均持有）+ 资源级归属链（Service 校验，非成员/任务不存在 → 404 `Task not found` 防枚举）。请求为 `multipart/form-data`，文件字段名 **`file`**；`Content-Type` 由客户端自报但**不采信**，一律按扩展名判定。201 返回 `AttachmentRead`（`id/task_id/uploader_id/uploader/filename/content_type/size/created_at`）。
  - **大小限制**：超过 `MAX_UPLOAD_SIZE`（默认 10485760 = 10MB）→ **413** `{"detail": "Uploaded file is too large"}`。校验在流式写入过程中按块累计，**不信任 Content-Length**；超限即中止并清理半成品文件，不产生任何元数据。
  - **MIME 白名单**：扩展名不在白名单（`png/jpg/jpeg/gif/webp/bmp/pdf/txt/md/csv/json/doc/docx/xls/xlsx/ppt/pptx/zip/gz`）或无扩展名 → **415** `{"detail": "File type is not allowed"}`。扩展名大小写不敏感（`.PNG` 通过）。**默认拒绝**：未列入的类型一律拒绝。
  - **文件名安全处理**：客户端文件名被清洗后仅作展示字段——去目录成分（POSIX `/` 与 Windows `\` 双分隔符）、去控制字符（含 CR/LF）、去首尾点与空白、折叠 Windows 保留设备名（`CON.txt` → `_CON.txt`）、超长时截断但保留扩展名。`../../../../etc/passwd.txt` → `passwd.txt`。
  - **不允许路径穿越**：磁盘 key 由服务端生成为 `tasks/{task_id}/{32位随机hex}{扩展名}`（如 `tasks/12/ab12cd34….pdf`），**不含任何用户输入**，因此同名文件重复上传互不覆盖；`storage_path` 落库为**相对 key**（不含绝对路径），存储层再做「解析后仍在根目录内」的结构层断言（双层防护）。注入后缀（如 `../../evil`）会被拒绝。
  - **空文件** → **400** `{"detail": "Uploaded file is empty"}`，已落盘的空文件即时回收。
- GET `/api/v1/tasks/{task_id}/attachments`（TASK-042）—— 附件列表。**功能级复用 `task:read`**（§6 权限清单无 attachment:read，附件属于任务，与评论列表同处理）+ 资源级归属链；`created_at` 升序，分页 `skip`/`limit`（`le=100`）；响应 `list[AttachmentRead]`。
- GET `/api/v1/attachments/{attachment_id}`（TASK-042）—— 下载附件。功能级 `attachment:download`（admin/member 均持有）+ 资源级归属链校验（§17「下载检查任务访问权限」）；不存在/不在归属链 → 404 `Attachment not found`（同文案防枚举）。
  - **响应为文件流**（非 JSON，因此不包 `SuccessResponse`）：`Content-Type` 为入库时的规范 MIME；`Content-Disposition: attachment; filename*=UTF-8''{百分号编码文件名}`（RFC 5987 形式，结构上杜绝响应头注入，非 ASCII 文件名如 `报告.pdf` 亦安全）；`Content-Length` 为入库 size；固定 `X-Content-Type-Options: nosniff`（阻止浏览器嗅探内容类型，防存储型 XSS）。
  - 元数据存在但物理文件缺失（外部清理/运维事故）→ 同样是 404 `Attachment not found`，而非 500（不泄露内部状态）。
- DELETE `/api/v1/attachments/{attachment_id}`（TASK-042，§17 清理要求）—— 删除附件。功能级**复用 `attachment:upload`**（§6 无 attachment:delete；能上传即能管理自己的上传物）+ 资源级 **上传者本人或任务所属团队 OWNER/ADMIN**（两者都不是 → 403 `Only team owner or admin or the uploader can delete attachments`）；不存在/不在归属链 → 404 `Attachment not found`（同文案防枚举）。
  - 删除顺序为**先删物理文件、再删元数据记录**：文件删除失败则不删记录并向上抛错（可重试），避免产生「记录没了、文件永久留在磁盘」的不可回收泄漏。
  - **写 OperationLog**：`action=attachment:delete`、`payload={task_id, attachment_id, filename}`，与删除同事务提交。
  - 删任务 / 删用户级联清附件**元数据**（FK ON DELETE CASCADE）；物理文件的批量回收由 Celery 清理任务负责（§17 / TASK-050）。

## Notification
- GET `/api/v1/notifications` —— 当前用户自己的通知时间线（TASK-053，资源级隔离）；按 `created_at DESC`，分页 `skip`/`limit`（`le=100`）；响应 `list[NotificationRead]`：`id / user_id / type / title / content / is_read / created_at`。仅认证（`CurrentUser`），无功能级权限（DECISIONS 035）。
- PATCH `/api/v1/notifications/read-all`（TASK-054）—— 把当前用户**全部未读**通知标记为已读；响应 `{"marked": N}`（N = 本次真正翻转的条数，重复调用幂等返回 0；空收件箱是合法的 0，不报 404）。仅认证；资源级隔离由 SQL WHERE `user_id` 保证，只动自己的收件箱。
- PATCH `/api/v1/notifications/{notification_id}/read` —— 标记自己的一条通知为已读；已在读幂等；非接收人 / 不存在 → 404 `Notification not found`（同文案防枚举）。

## Logs
- GET `/api/v1/logs` —— 操作审计日志（TASK-039）。功能级 `log:read`（admin/member 均持有）；**仅返回当前用户自己**的日志（资源级隔离，最小暴露面）；分页 `skip`/`limit`（`le=100`）；响应 `list[OperationLogRead]`：`id / user_id / resource_type / resource_id / action / payload(JSONB) / created_at`，按 `created_at DESC`。
- GET `/api/v1/logs/{resource_type}/{resource_id}` —— 某资源的操作日志；功能级 `log:read` + **资源级归属校验**（task：调用者须在目标任务的团队链上，否则 404 防枚举；非 `task` 资源类型 → 404 暂不支持）；分页同 `GET /logs`。
- 埋点：TASK-038 `POST /tasks/{task_id}/transition` 成功时，在同一事务内写入 `action=task:transition`、`payload={old_status, new_status}` 的日志（§15 示例字段）。

## Health
- GET `/health`
- GET `/health/db`
- GET `/health/redis`

## 响应
成功：`data` + `message`；分页：`data/page/page_size/total`；错误通过 HTTP 状态码与 `detail` 表达。

> 具体 Request/Response 字段若尚未在源项目文档中定义，不在初始化阶段擅自虚构，标记为待实现/待确认。
