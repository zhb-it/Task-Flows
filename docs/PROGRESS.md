# TaskFlow Pro 当前进度

## Project Status
In Progress

## Current Phase
Phase 2：用户与认证

## Current Task
TASK-017 `/users/me`（已完成）

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
- [x] TASK-058 Dockerfile（因 TASK-009 要求在 Docker 中部署而提前完成并验证）

## In Progress
- [ ]

## Blocked
- None

## Next
TASK-018 Refresh Token/JTI（Phase 2 用户与认证）

## 部署状态
Docker 全栈已启动并验证：taskflow-app(:8000) / taskflow-postgres(宿主 5433→5432) / taskflow-redis(宿主 6389→6379) 均 healthy；`GET /health` 返回 `{"status":"ok","database":"up","redis":"up"}`。
TASK-017 完成后已用 `docker compose up -d --build` 重建 app 镜像，并在真实容器上端到端验证 `GET /api/v1/users/me`：有效 Token → 200（字段与注册返回一致、不泄露密码）；无 Token / 篡改签名 → 401 且带 `WWW-Authenticate: Bearer`；账号禁用 → 403；账号删除 → 401。验证后开发库 users 表 0 行残留。

## 规则
只有真实完成并验证后才能勾选 Completed。
