# API Contract

> 本文件只登记项目开发文档中已经明确的 API。后续新增 API 必须同步更新本文件。

## 基础路径
`/api/v1`

## Auth
- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

## 授权机制（TASK-023，内部机制，无独立端点）
后续资源端点通过权限依赖 `require_permission("resource:action", ...)` 声明所需权限（多值 AND 语义）：

- 未认证（无/非法 Token）→ `401` + `WWW-Authenticate: Bearer`（与 `/users/me` 一致）。
- 已认证但账号禁用 → `403` `{"detail": "User account is disabled"}`。
- 已认证但缺少所需权限 → `403` `{"detail": "Permission denied: <缺失的权限名, 逗号分隔>"}`（多权限 AND 时只列出缺失项）。
- 权限名严格 `resource:action` 格式（§6），用户有效权限 = 其全部角色的权限并集（去重）。
- 种子角色（TASK-022）：`admin` 持有全部 22 项权限；`member` 持有 10 项「读 + 基础写」。

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

## Team
- POST `/api/v1/teams`
- GET `/api/v1/teams`
- GET `/api/v1/teams/{team_id}`
- PATCH `/api/v1/teams/{team_id}`
- DELETE `/api/v1/teams/{team_id}`
- POST `/api/v1/teams/{team_id}/members`
- GET `/api/v1/teams/{team_id}/members`
- DELETE `/api/v1/teams/{team_id}/members/{user_id}`

## Project
- POST `/api/v1/projects`
- GET `/api/v1/projects`
- GET `/api/v1/projects/{project_id}`
- PATCH `/api/v1/projects/{project_id}`
- DELETE `/api/v1/projects/{project_id}`

## Task
- POST `/api/v1/tasks`
- GET `/api/v1/tasks`
- GET `/api/v1/tasks/{task_id}`
- PATCH `/api/v1/tasks/{task_id}`
- DELETE `/api/v1/tasks/{task_id}`
- POST `/api/v1/tasks/{task_id}/transition`
- POST `/api/v1/tasks/{task_id}/assignees`
- DELETE `/api/v1/tasks/{task_id}/assignees/{user_id}`

## Comment
- POST `/api/v1/tasks/{task_id}/comments`
- GET `/api/v1/tasks/{task_id}/comments`
- DELETE `/api/v1/comments/{comment_id}`

## Attachment
- POST `/api/v1/tasks/{task_id}/attachments`
- GET `/api/v1/attachments/{attachment_id}`
- DELETE `/api/v1/attachments/{attachment_id}`

## Notification
- GET `/api/v1/notifications`
- PATCH `/api/v1/notifications/{notification_id}/read`
- PATCH `/api/v1/notifications/read-all`

## Logs
- GET `/api/v1/logs`
- GET `/api/v1/logs/{resource_type}/{resource_id}`

## Health
- GET `/health`
- GET `/health/db`
- GET `/health/redis`

## 响应
成功：`data` + `message`；分页：`data/page/page_size/total`；错误通过 HTTP 状态码与 `detail` 表达。

> 具体 Request/Response 字段若尚未在源项目文档中定义，不在初始化阶段擅自虚构，标记为待实现/待确认。
