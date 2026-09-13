# TaskFlow Pro 开发任务

## Phase 1：项目基础设施
- [x] TASK-001 初始化 Git 与 Python 项目骨架
- [x] TASK-002 配置基础依赖与环境变量
- [x] TASK-003 创建 FastAPI 应用与基础配置
- [x] TASK-004 配置 PostgreSQL Docker 服务
- [x] TASK-005 配置 Redis Docker 服务
- [x] TASK-006 配置 SQLAlchemy Async Session/Base
- [x] TASK-007 初始化 Alembic
- [x] TASK-008 实现 `/health`
- [x] TASK-009 启动 Compose 并验证 API/PostgreSQL/Redis
- [x] TASK-010 第一次 Git Commit

## Phase 2：用户与认证
- [x] TASK-011 User Model
- [x] TASK-012 User Migration
- [x] TASK-013 User Schema/CRUD
- [x] TASK-014 密码哈希与安全模块
- [x] TASK-015 注册
- [x] TASK-016 登录与 Access Token
- [x] TASK-017 `/users/me`
- [x] TASK-018 Refresh Token/JTI
- [ ] TASK-019 Logout/Token revoke
- [ ] TASK-020 Auth 测试

## Phase 3：RBAC
- [ ] TASK-021 Role/Permission Model
- [ ] TASK-022 RBAC Migration/CRUD
- [ ] TASK-023 权限依赖
- [ ] TASK-024 Service 资源级权限
- [ ] TASK-025 RBAC 测试

## Phase 4：团队与项目
- [ ] TASK-026 Team/TeamMember
- [ ] TASK-027 团队 CRUD
- [ ] TASK-028 成员邀请/删除
- [ ] TASK-029 Project Model/CRUD/Service/Router
- [ ] TASK-030 团队与项目权限测试

## Phase 5：任务核心
- [ ] TASK-031 Task Model/Migration
- [ ] TASK-032 Task Schema/CRUD
- [ ] TASK-033 Task Service
- [ ] TASK-034 Task API
- [ ] TASK-035 Task 查询过滤/分页/排序
- [ ] TASK-036 TaskAssignee 多人分配

## Phase 6：状态机与审计
- [ ] TASK-037 状态机规则
- [ ] TASK-038 Transition API
- [ ] TASK-039 OperationLog
- [ ] TASK-040 状态机与审计测试

## Phase 7：评论与附件
- [ ] TASK-041 Comment
- [ ] TASK-042 Attachment
- [ ] TASK-043 上传/下载权限与安全校验
- [ ] TASK-044 评论/附件测试

## Phase 8：Redis 与 Celery
- [ ] TASK-045 Redis 连接与 Key 约定
- [ ] TASK-046 ZSET + Lua 滑动窗口限流
- [ ] TASK-047 限流测试
- [ ] TASK-048 Celery App/Worker
- [ ] TASK-049 通知异步任务
- [ ] TASK-050 日志归档/附件清理任务
- [ ] TASK-051 幂等、重试与任务测试

## Phase 9：通知
- [ ] TASK-052 Notification Model
- [ ] TASK-053 通知 Service/API
- [ ] TASK-054 已读/未读
- [ ] TASK-055 通知测试

## Phase 10：工程化
- [ ] TASK-056 结构化日志
- [ ] TASK-057 Request ID
- [x] TASK-058 Dockerfile
- [ ] TASK-059 Production Compose
- [ ] TASK-060 Nginx/Gunicorn/Uvicorn
- [ ] TASK-061 GitHub Actions CI
- [ ] TASK-062 完整测试与质量检查
- [ ] TASK-063 README 与面试技术难点

## TASK 执行规则
每个 TASK 必须包含：目标、依赖、涉及文件、实现要求、验收标准、测试要求。
一次只执行一个 TASK；测试未通过不得标记完成。
