# TaskFlow Pro 当前进度

## Project Status
In Progress

## Current Phase
Phase 2：用户与认证

## Current Task
TASK-018 Refresh Token/JTI（已完成）

## Completed
- [x] TASK-001 初始化 Git 与 Python 项目骨架
- [x] TASK-002 配置基础依赖与环境变量
- [x] TASK-003 创建 FastAPI 应用与基础配置
- [x] TASK-004 配置 PostgreSQL Docker 服务
- [x] TASK-005 配置 Redis Docker 服务
- [x] TASK-006 配置 SQLAlchemy Async Session/Base
- [x] TASK-007 初始化 Alembic
- [x] TASK-008 实现 /health
- [x] TASK-009 启动 Compose 并验证 API/PostgreSQL/Redis
- [x] TASK-010 第一次 Git Commit
- [x] TASK-011 User Model
- [x] TASK-012 User Migration
- [x] TASK-013 User Schema/CRUD
- [x] TASK-014 密码哈希与安全模块
- [x] TASK-015 注册
- [x] TASK-016 登录与 Access Token
- [x] TASK-017 `/users/me`
- [x] TASK-018 Refresh Token/JTI
- [x] TASK-058 Dockerfile（因 TASK-009 要求在 Docker 中部署而提前完成并验证）

## In Progress
- [ ]

## Blocked
- None

## Next
TASK-019 Logout/Token revoke（Phase 2 用户与认证）

## 部署状态
Docker 全栈已启动并验证：taskflow-app(:8000) / taskflow-postgres(宿主 5433→5432) / taskflow-redis(宿主 6389→6379) 均 healthy；`GET /health` 返回 `{"status":"ok","database":"up","redis":"up"}`。
TASK-018 完成后已重建 app 镜像，并在真实容器上端到端验证双 Token 流程：login 返回 `access_token` + `refresh_token`；refresh 轮换成功且新 Access Token 可访问 `/users/me`；旧 Refresh Token 复用 401；Access Token 冒充 Refresh Token 401；篡改 401；缺字段 422；账号禁用后 refresh 403、恢复启用后同一 Token 又能成功（证明 403 确由账号状态引起）；库中只有 jti（旧 jti `revoked=true`、新 jti `revoked=false`）、Token 本体不落库；删除用户后 `refresh_tokens` 被级联清理。验证后 users 与 refresh_tokens 两表均 0 行残留。

## 规则
只有真实完成并验证后才能勾选 Completed。
