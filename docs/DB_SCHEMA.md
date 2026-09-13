# TaskFlow Pro 数据库设计

## 数据库
PostgreSQL 16。

## 核心实体
User、Role、Permission、UserRole、RolePermission、Team、TeamMember、Project、Task、TaskAssignee、Comment、Attachment、OperationLog、Notification、RefreshToken。

## 关键关系
- User -> UserRole -> Role -> RolePermission -> Permission
- Team -> TeamMember -> User
- Team -> Project
- Project -> Task
- Task -> TaskAssignee -> User
- Task -> Comment
- Task -> Attachment
- User -> OperationLog
- User -> Notification
- User -> RefreshToken

## refresh_tokens（TASK-018 已实现）
字段取自开发文档 §19「JWT 双 Token」：

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| user_id | BIGINT | NOT NULL，FK → `users(id)` ON DELETE CASCADE，索引 |
| jti | VARCHAR(36) | NOT NULL，UNIQUE |
| expires_at | TIMESTAMPTZ | NOT NULL |
| revoked | BOOLEAN | NOT NULL，DEFAULT false |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |

- 只存 Refresh Token 的 `jti`，Token 本体永不落库（§55.1「保存 Refresh Token JTI」）。
- `ON DELETE CASCADE`：删除用户即清理其全部 Token 记录，不留孤儿行。
- 撤销（TASK-019）与轮换（TASK-018）均按 `jti` 定位。
- 迁移：`migrations/versions/872a33b812af_create_refresh_tokens.py`。

## RBAC 四表（TASK-021 模型已定义，迁移属 TASK-022）
开发文档 §6 只给出表名与模型链（User → UserRole → Role → RolePermission → Permission），未定义列。以下为 TASK-021 确认的推断设计，作为后续迁移与 CRUD 的契约：

**roles**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| name | VARCHAR(64) | NOT NULL，UNIQUE —— 角色标识（如 `admin` / `member`） |
| description | VARCHAR(255) | 可空 |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新 |

**permissions**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| name | VARCHAR(100) | NOT NULL，UNIQUE —— 严格 `resource:action` 格式（§6 示例），单列不拆分 |
| description | VARCHAR(255) | 可空 |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新 |

**user_roles**（纯关联表，不带时间戳）

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| user_id | BIGINT | NOT NULL，FK → `users(id)` ON DELETE CASCADE，索引 |
| role_id | BIGINT | NOT NULL，FK → `roles(id)` ON DELETE CASCADE，索引 |
| 复合 UNIQUE `(user_id, role_id)` | | 同一用户不可重复授予同一角色 |

**role_permissions**（纯关联表，不带时间戳）

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| role_id | BIGINT | NOT NULL，FK → `roles(id)` ON DELETE CASCADE，索引 |
| permission_id | BIGINT | NOT NULL，FK → `permissions(id)` ON DELETE CASCADE，索引 |
| 复合 UNIQUE `(role_id, permission_id)` | | 同一角色不可重复绑定同一权限 |

- 权限判断以 `resource:action` 字符串为键（如 `user:read`），由 TASK-023 权限依赖消费。
- `ON DELETE CASCADE`：删除用户/角色/权限时关联记录一并清理，不产生悬挂授权。
- 迁移：`migrations/versions/7e15047d3a10_create_rbac_tables.py`（建表）+ `migrations/versions/0de65c197efc_seed_rbac_data.py`（种子，TASK-022）。
- 种子数据（TASK-022 决策）：角色 `admin` / `member`；权限为开发文档 §6 全部 **22 项** `resource:action` 权限；`admin` 绑定全部 22 项，`member` 授「读 + 基础写」10 项（`user:read`、`team:read`、`project:read`、`task:read`、`log:read` + `task:create`、`task:update`、`comment:create`、`attachment:upload`、`attachment:download`）。全部 INSERT 带 `ON CONFLICT DO NOTHING`，幂等可重放；降级仅按 name 删除种子行。此为开发文档 §56 Phase 4「ADMIN / MEMBER 权限表现不同」验收的数据前提。

## 团队两表（TASK-026 已实现）
字段取自开发文档 §7。TASK-026 决策（已确认）：

**teams**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| name | VARCHAR(150) | NOT NULL，**不加 UNIQUE**（§7 未定义唯一约束，同名团队靠 id 区分） |
| description | VARCHAR(255) | 可空 |
| owner_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE RESTRICT**，索引 —— 团队是聚合根，owner 被删前必须先转让所有权，不得静默级联删团队 |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新 |

**team_members**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| team_id | BIGINT | NOT NULL，FK → `teams(id)` ON DELETE CASCADE，索引 |
| user_id | BIGINT | NOT NULL，FK → `users(id)` ON DELETE CASCADE，索引 |
| role_id | SMALLINT | NOT NULL，CHECK `role_id IN (1, 2, 3)` —— **团队角色**：1=OWNER / 2=ADMIN / 3=MEMBER（§7 示例），与全局 RBAC 角色（`roles` 表，管 `resource:action` 功能权限）是两个维度 |
| joined_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| 复合 UNIQUE `(team_id, user_id)` | | §7「一个用户不能重复加入同一个团队」 |

- 团队角色（OWNER/ADMIN/MEMBER）管团队内的地位（能否邀请/删人等，§35「非管理员不能邀请」的消费方），**不参与** `get_user_permissions` 的功能权限解析。
- **业务规则（TASK-027 决策）**：创建团队时 Service 层在同一事务内自动写入一条 `team_members(owner, role_id=1)` OWNER 行——成员归属链统一以 `team_members` 为准。
- 迁移：`migrations/versions/fc52c0603ba5_create_teams_and_team_members.py`。

## 项目表（TASK-029 已实现）
源开发文档未定义 projects 字段（§7 只给到团队），以下为 TASK-029 用户确认的决策：

**projects**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| name | VARCHAR(150) | NOT NULL，**不加 UNIQUE**（源文档未定义唯一约束） |
| description | VARCHAR(255) | 可空 |
| team_id | BIGINT | NOT NULL，FK → `teams(id)` **ON DELETE CASCADE**，索引 —— 项目是团队资产，删团队级联清项目（未来其下任务随之清理） |
| owner_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE RESTRICT**，索引 —— 记录创建者（可后续转让），与 teams.owner_id 同语义：删用户前必须先处理其项目 |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新 |

- 关系链遵循 DB_SCHEMA 顶层 `Team -> Project -> Task`；可见性按规格 §5「用户只能访问其所属团队链路下的资源」——项目所属团队的 `team_members` 成员构成归属链。
- 迁移：`migrations/versions/99f70df5d269_create_projects_table.py`（autogenerate，`information_schema` 实证 CASCADE/RESTRICT 与双索引）。

## 已明确约束
- User.username UNIQUE
- User.email UNIQUE
- RefreshToken.jti UNIQUE
- Role.name UNIQUE
- Permission.name UNIQUE（`resource:action` 格式）
- UserRole(user_id, role_id) 不允许重复
- RolePermission(role_id, permission_id) 不允许重复
- TeamMember(team_id, user_id) 不允许重复
- TaskAssignee(task_id, user_id) UNIQUE
- Task status CHECK：TODO / IN_PROGRESS / REVIEW / DONE / CANCELLED
- Task priority CHECK：LOW / MEDIUM / HIGH / URGENT
- 必要外键、NOT NULL、CHECK、唯一约束优先由数据库兜底

## Task 索引
- `(project_id, status)`
- `(creator_id)`
- `due_at` 部分索引：未完成/未取消任务

## PostgreSQL 能力
- JSONB：OperationLog payload
- GIN：JSONB 与搜索
- pg_trgm：标题模糊搜索
- tsvector：任务标题+描述全文搜索

## 注意
具体字段类型、级联策略和全部索引在实现对应 Model 时逐项确认，不凭空增加字段。
