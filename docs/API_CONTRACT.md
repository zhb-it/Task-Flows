# API Contract

> 本文件只登记项目开发文档中已经明确的 API。后续新增 API 必须同步更新本文件。

## 基础路径
`/api/v1`

## Auth
- POST `/api/v1/auth/register`
- POST `/api/v1/auth/login`
- POST `/api/v1/auth/refresh`
- POST `/api/v1/auth/logout`

## User
- GET `/api/v1/users/me`

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
