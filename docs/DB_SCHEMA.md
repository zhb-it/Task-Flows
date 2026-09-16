# TaskFlow Pro 数据库设计

## 数据库
PostgreSQL 16。

## 核心实体
Tenant、User、Role、Permission、UserRole、RolePermission、Team、TeamMember、Project、Task、TaskAssignee、Comment、Attachment、OperationLog、Notification、RefreshToken。

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
- Tenant（TASK-093：独立顶层实体）
- Tenant -> 12 张业务表（TASK-094：users/refresh_tokens/teams/team_members/projects/tasks/
  task_assignees/comments/attachments/operation_logs/operation_logs_archive/notifications
  经 tenant_id FK 归属，ON DELETE RESTRICT；RBAC 三表 + permissions 的租户化属 TASK-096）

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

## 任务表（TASK-031 已实现）
源开发文档未定义 tasks 字段，以下为 TASK-031 用户确认的决策；DB_SCHEMA 硬约束（status/priority CHECK 值集、Task 索引清单）全部落实：

**tasks**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| project_id | BIGINT | NOT NULL，FK → `projects(id)` **ON DELETE CASCADE**——任务随项目级联清理（Project -> Task 链） |
| title | VARCHAR(200) | NOT NULL，**不加 UNIQUE**（同项目同名任务可并存） |
| description | TEXT | 可空 |
| status | VARCHAR(20) | NOT NULL，DEFAULT `'TODO'`，CHECK `IN ('TODO','IN_PROGRESS','REVIEW','DONE','CANCELLED')`——存字面字符串，API/DB/日志同字面值；状态流转由状态机（TASK-037）与 transition API（TASK-038）消费，**不允许经普通 PATCH 修改**（规格 §5 / Decision 005） |
| priority | VARCHAR(10) | NOT NULL，DEFAULT `'MEDIUM'`，CHECK `IN ('LOW','MEDIUM','HIGH','URGENT')` |
| creator_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE CASCADE**，索引——creator 是创建者而非 owner 式所有者，删用户级联清其创建的任务，不卡用户删除；审计追溯由 OperationLog（TASK-039）承担 |
| due_at | TIMESTAMPTZ | 可空 |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新 |
| search_vector | TSVECTOR | 可空，**DB 端生成列**（TASK-064，规格 §14）：`GENERATED ALWAYS AS (to_tsvector('simple', coalesce(title,'') \|\| ' ' \|\| coalesce(description,''))) STORED`。应用**只读不写**（ORM 侧 `Computed`，SQLAlchemy 自动把它排除在 INSERT/UPDATE 之外） |

- **无 assignee 列**：多人分配由 `task_assignees`（TASK-036）承担，`UNIQUE(task_id, user_id)`（规格 §5）。
- **索引（DB_SCHEMA「Task 索引」清单）**：复合 `(project_id, status)`、`(creator_id)`、`due_at` 部分索引 `WHERE status IN ('TODO','IN_PROGRESS','REVIEW')`（仅未完成/未取消任务）。
- **搜索索引（TASK-064，规格 §14）**：`GIN (title gin_trgm_ops)`（`ix_tasks_title_trgm`，需 `pg_trgm` 扩展）与 `GIN (search_vector)`（`ix_tasks_search_vector`）。前者让 `keyword` 的 `ILIKE '%x%'` 走索引（B-tree 对非锚定模式无效）；后者支撑全文检索。`keyword` 查询语义**未变**——仍是标题 ILIKE，见 `docs/API_CONTRACT.md`。
- 迁移：`migrations/versions/6f1cfcc35abe_create_tasks_table.py`（autogenerate，pg_constraint / pg_indexes / information_schema 实证双 CHECK、双 CASCADE、部分索引谓词）；`migrations/versions/6765bdcfa73e_add_task_search_indexes_and_search_vector.py`（TASK-064，`CREATE EXTENSION pg_trgm` + 生成列 + 两个 GIN 索引）。

## 任务分配表（TASK-036 已实现）
规格 §5 硬约束 `UNIQUE(task_id, user_id)` 由**复合主键**天然落实。源文档未定义该表字段，`assigned_by_id` 为 TASK-036 推断设计（最小审计——记录谁做的分配，追溯由 OperationLog TASK-039 承担）：

**task_assignees**

| 列 | 类型 | 约束 |
|---|---|---|
| task_id | BIGINT | **复合主键之一**，FK → `tasks(id)` **ON DELETE CASCADE**——删任务清分配行 |
| user_id | BIGINT | **复合主键之一**，FK → `users(id)` **ON DELETE CASCADE**，单列索引——删用户清分配行不卡删除（与 creator_id 同决策），索引服务于 assignee_id 过滤与「我的任务」反查 |
| assigned_by_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE CASCADE**——分配操作者（推断设计） |
| assigned_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，内嵌响应按此升序 |

- 复合主键 `(task_id, user_id)` = 规格 §5 的 UNIQUE 约束（information_schema / pg_indexes 实证：`task_assignees_pkey` + `ix_task_assignees_user_id`）。
- 不建 Task -> assignees relationship（延续 TASK-031 决策）：读取由 Service 批量 IN 查询组装 TaskRead.assignees（列表场景避免 N+1）。
- 迁移：`migrations/versions/b90b4cff0f64_create_task_assignees.py`（autogenerate，information_schema 实证复合 PK、三 FK 全 CASCADE、user_id 索引）。

## 评论表（TASK-041 已实现）
字段取自开发文档 §16。TASK-041 用户确认的决策：

**comments**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| task_id | BIGINT | NOT NULL，FK → `tasks(id)` **ON DELETE CASCADE**——评论必须属于任务（§16 规则 2），删任务级联清其全部评论 |
| user_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE CASCADE**，索引——评论是用户产出内容，删用户级联清其评论（与 `tasks.creator_id` 同惯例） |
| content | TEXT | NOT NULL，非空由 Schema 校验（1–2000 字符） |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now()，更新时刷新——本 TASK 不做编辑端点（§25.6 仅 POST/GET/DELETE），编辑能力留后续 |

- 索引 `(task_id, created_at)`：评论列表按任务维度 + 时间序查询的主访问路径（§16 未显式定义，按查询模式推断）。
- 删除评论写 `action=comment:delete` 审计日志（§16 规则 4，复用 OperationLog）。
- 迁移：`migrations/versions/d7a3b9c1e5f2_create_comments.py`。

## 附件表（TASK-042 已实现）
字段取自开发文档 §17。TASK-042 用户确认的决策：

**attachments**

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| task_id | BIGINT | NOT NULL，FK → `tasks(id)` **ON DELETE CASCADE**——附件必须属于任务（§17），删任务级联清其附件元数据 |
| uploader_id | BIGINT | NOT NULL，FK → `users(id)` **ON DELETE CASCADE**，索引——附件是用户产出内容，删用户级联清其元数据 |
| filename | VARCHAR(255) | NOT NULL——**清洗后**的安全文件名（去目录分隔符/控制字符/首尾点空白、折叠 Windows 保留设备名、截断保留扩展名），仅用于展示与下载响应，**不参与路径构造** |
| storage_path | VARCHAR(512) | NOT NULL，**UNIQUE**——相对存储 key（如 `tasks/12/ab12cd34.bin`），不含绝对路径；物理位置由 `UPLOAD_DIR` 决定，DB 不绑定部署机器的文件系统布局（§17 预留对象存储迁移） |
| content_type | VARCHAR(255) | NOT NULL——按**扩展名白名单**校验后的规范 MIME，不采信客户端自报的 Content-Type |
| size | BIGINT | NOT NULL——**实际写入字节数**（流式落盘累计），不信任 Content-Length |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |

- 无 CHECK 约束：§17 未定义枚举值集，size/content_type 合法性由 Service 层保证（项目规则 §6）。
- 索引：`(task_id, created_at)`（附件列表主访问路径）、`storage_path` UNIQUE（防同 key 覆盖）、`(uploader_id)`。
- §17 上传要求全部在 Service 层实现：大小限制（10MB，超限 413）、MIME 白名单（415）、文件名安全处理、路径穿越防护（双层：语义校验 + 解析后越界断言）、下载检查任务访问权限（归属链 404）。
- 删除附件写 `action=attachment:delete` 审计日志。
- 删任务/删用户级联清附件**元数据**；物理文件由 Celery 清理任务负责（§17 / TASK-050）。
- 迁移：`migrations/versions/e9b4c2d6f8a1_create_attachments.py`。


## tenants（TASK-093 已实现）

平台 → 租户 → 用户/团队/项目 的顶层边界实体（§61.3 多租户）。列定稿为本 TASK
拍板（决策全文 docs/DECISIONS.md 065）：

| 列 | 类型 | 约束 |
|---|---|---|
| id | BIGINT | PRIMARY KEY，自增 |
| name | VARCHAR(150) | NOT NULL（不加 UNIQUE，与 teams.name 同口径） |
| slug | VARCHAR(63) | NOT NULL，UNIQUE（`uq_tenants_slug`），CHECK 格式 `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`；对外标识，创建后不可变 |
| status | VARCHAR(16) | NOT NULL，DEFAULT 'active'，CHECK IN ('active','suspended','deleted')；转换白名单（active↔suspended、→deleted 单向）由 Service 执行 |
| member_limit | INTEGER | 可空，NULL = 未设限，CHECK (> 0) |
| storage_limit_bytes | BIGINT | 可空，NULL = 未设限，CHECK (>= 0) |
| created_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |
| updated_at | TIMESTAMPTZ | NOT NULL，DEFAULT now() |

- `deleted` 是**状态而非物理删除**：行保留，其 slug 依旧占用（复用等于让新租户继承旧租户的对外标识与历史）。
- 配额的「执行」（成员数/存储量强制点）在后续任务接入对应业务表时实现；本表只定存储。
- 本 TASK 不接业务表（无被引用外键，级联行为集合为空）；TASK-094 落 `tenant_id` 后由其迁移与测试补级联断言。
- 配套种子：权限 `tenant:manage`（平台管理员能力面，只授予全局 `admin` 角色）。
- 迁移：`migrations/versions/c7d1e8f4a2b6_create_tenants.py`。

## 业务表租户化（TASK-094 已实现）

§61.3 / §5 修订的落库形态（决策全文 docs/DECISIONS.md 066）：

- **归属**：12 张业务表有 `tenant_id BIGINT NOT NULL`，FK → `tenants(id)` ON DELETE
  RESTRICT，索引 `ix_<table>_tenant_id`（tenant_id 前导）；迁移 f1a2c3d4e5b6。
- **唯一性租户化**：`users` 的 username/email 唯一性由 `(tenant_id, username)` /
  `(tenant_id, email)` 复合约束（`uq_users_tenant_username` / `uq_users_tenant_email`）
  承担，全局唯一已删除；全局查询留 `ix_users_username` / `ix_users_email` 过渡索引。
  `refresh_tokens.jti`、`attachments.storage_path`、`tenants.slug` 保持全局唯一（系统
  生成的技术标识，防跨租户混淆）。
- **存量回填**：默认租户 `slug='default'`（name='Default Tenant'），全部存量行挂靠，
  零孤儿；迁移 a9b7c5d3e1f0，幂等可重放，downgrade 不还原数据（归属是事实初始化）。
- **写入桥接**：各业务表 `tenant_id` 的列 DEFAULT 为 `current_default_tenant_id()`
  （STABLE 函数查默认租户）——INSERT 未赋值时由 DB 归属默认租户；应用层显式赋值
  优先。TASK-095 落认证租户后本层退化为兜底。
- **附件存储**：新上传 key 为 `tenants/{tenant_id}/tasks/{task_id}/{random}`；存量
  旧 key（`tasks/...`）读取不受影响。

## 行级安全（RLS）兜底与运行时角色（TASK-095 已实现）

§61.3「应用层统一作用域 + PostgreSQL RLS 兜底」的落库形态（决策全文
docs/DECISIONS.md 067）：

- **app schema 两个 STABLE 函数**：`app.current_tenant_id()` 读事务级 GUC
  `app.tenant_id`（未设返回 NULL）；`app.rls_bypass()` 读
  `app.tenant_bypass = 'on'`。应用在每个事务开始经 `SET LOCAL` 写入
  （`after_begin` 事件：有租户上下文写 tenant，无上下文/显式出口写 bypass）。
- **12 张业务表 ENABLE + FORCE ROW LEVEL SECURITY + 策略 `tenant_isolation`**：
  USING/WITH CHECK 均为 `tenant_id = app.current_tenant_id() OR app.rls_bypass()`。
  租户内请求 fail-closed（应用层漏加条件时 RLS 仍拦）；登录前/Celery/系统
  任务走 bypass 分支不受影响。迁移 `b8d4f2a6c9e1_row_level_security.py`，
  downgrade 全量回退（策略 → RLS 开关 → app schema → 角色；角色在集群其他
  库仍有授权时保留并 NOTICE）。
- **运行时角色 `taskflow_app`**：超级用户（postgres）按语义绕过 RLS，运行时
  应用连接必须使用本角色（LOGIN；compose 三个服务已切换）。角色获得
  public schema 的表/序列操作授权 + 未来新表的默认权限；迁移与测试夹具
  保持超管。生产须轮换密码（`ALTER ROLE taskflow_app WITH PASSWORD ...` +
  compose `TASKFLOW_APP_DB_PASSWORD`）。
- **作用域标记**：12 个业务模型继承 `TenantScoped` mixin
  （`app/core/tenant_context.py`）；RBAC 表与 tenants 不参与租户作用域。

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
- Attachment.storage_path UNIQUE
- Task status CHECK：TODO / IN_PROGRESS / REVIEW / DONE / CANCELLED
- Task priority CHECK：LOW / MEDIUM / HIGH / URGENT
- 必要外键、NOT NULL、CHECK、唯一约束优先由数据库兜底

## Task 索引
- `(project_id, status)`
- `(creator_id)`
- `due_at` 部分索引：未完成/未取消任务
- `GIN (title gin_trgm_ops)`（TASK-064）：模糊匹配索引，`ILIKE '%x%'` 可用
- `GIN (search_vector)`（TASK-064）：全文检索索引

## PostgreSQL 能力
- JSONB：OperationLog payload
- GIN：JSONB 与搜索
- pg_trgm：标题模糊搜索（TASK-064 已实现——`CREATE EXTENSION pg_trgm` + `ix_tasks_title_trgm`）
- tsvector：任务标题+描述全文搜索（TASK-064 已实现——`tasks.search_vector` 生成列 + `ix_tasks_search_vector`；注意 `'simple'` 配置**不做中文分词**，故 `keyword` 仍走 `ILIKE`，见 DECISIONS 045）

## 注意
具体字段类型、级联策略和全部索引在实现对应 Model 时逐项确认，不凭空增加字段。
