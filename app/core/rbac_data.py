"""RBAC 权限与角色常量（TASK-096，§61.3.4 租户内 RBAC）.

集中定义平台能力面的权限集合与角色→权限映射，供 `rbac_seed` 在**每个租户**
内幂等播种，以及文档/迁移复用同一份事实来源（避免散落字符串漂移）。

关键边界（DECISIONS 062 / TASK-096）：

- ``tenant:manage`` 是**平台权限**，刻意**不**出现在本模块——它只授予默认租户
  的 admin（由种子迁移 c7d1e8f4a2b6 在全局 admin 上绑定，TASK-094/095 回溯回填
  后归属默认租户）。普通租户（create_tenant_with_checks 创建的）的 admin 永远
  不持有它，因此租户管理员无法越权管理其他租户。
- 权限是**全局目录**（permissions 表不随租户复制）；角色与授权关系是**租户内**
  实体（roles / role_permissions / user_roles 带 tenant_id，由 RLS 兜底）。
- ``ALL_PERMISSIONS`` 是开发文档 §6 列出的全部 22 项 ``resource:action`` 能力，
  不含平台权限。
"""

from __future__ import annotations

#: 角色标识（种子保证每个租户内存在且 name 唯一）。
ADMIN_ROLE_NAME = "admin"
MEMBER_ROLE_NAME = "member"

#: 开发文档 §6 的全部 22 项权限（resource:action 格式），不含平台权限
#: ``tenant:manage``。这是「租户内 admin 角色」应持有的完整能力集。
ALL_PERMISSIONS: tuple[str, ...] = (
    "user:read",
    "user:update",
    "team:create",
    "team:read",
    "team:update",
    "team:delete",
    "team:invite",
    "project:create",
    "project:read",
    "project:update",
    "project:delete",
    "task:create",
    "task:read",
    "task:update",
    "task:delete",
    "task:assign",
    "task:transition",
    "comment:create",
    "comment:delete",
    "attachment:upload",
    "attachment:download",
    "log:read",
)

#: member 的「读 + 基础写」子集（TASK-022 决策，10 项）。
MEMBER_PERMISSIONS: tuple[str, ...] = (
    "user:read",
    "team:read",
    "project:read",
    "task:read",
    "log:read",
    "task:create",
    "task:update",
    "comment:create",
    "attachment:upload",
    "attachment:download",
)

#: 各角色应持有的权限集合（不含平台权限）；create_tenant_with_checks 据此播种。
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    ADMIN_ROLE_NAME: ALL_PERMISSIONS,
    MEMBER_ROLE_NAME: MEMBER_PERMISSIONS,
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    ADMIN_ROLE_NAME: "Administrator - full access to all resources within the tenant",
    MEMBER_ROLE_NAME: "Regular member - read access plus basic write operations",
}
