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

## 已明确约束
- User.username UNIQUE
- User.email UNIQUE
- RefreshToken.jti UNIQUE
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
