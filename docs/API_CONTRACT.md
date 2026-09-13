# API Contract

> 本文件只登记项目开发文档中已经明确的 API。后续新增 API 必须同步更新本文件。

## 基础路径
`/api/v1`

## Auth
- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

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

### POST `/api/v1/auth/login`（TASK-016 已实现）

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
    "token_type": "bearer"
  },
  "message": "success"
}
```

- `access_token` 为 HS256 签名的 JWT，claims：`sub`（用户 id，字符串）、`type`（`"access"`）、`iat`、`exp`（默认 30 分钟后过期，由 `ACCESS_TOKEN_EXPIRE_MINUTES` 控制）。
- 客户端使用方式：`Authorization: Bearer <access_token>`。
- 用户名不存在或密码错误 → `401 Unauthorized`：`{"detail": "Invalid username or password"}`（两种情形文案一致，避免用户名枚举），响应头含 `WWW-Authenticate: Bearer`。
- 密码正确但账号被禁用（`is_active=false`）→ `403 Forbidden`：`{"detail": "User account is disabled"}`。
- 缺少必填字段 → `422 Unprocessable Entity`。
- 响应永不包含 `password` 或 `password_hash`。
- 本 TASK 只签发 Access Token；Refresh Token / JTI（`POST /api/v1/auth/refresh`）属 TASK-018。

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
