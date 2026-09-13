"""seed rbac data

TASK-022 种子数据（用户确认的决策）：
- 角色：admin / member。
- 权限：开发文档 §6 的全部 22 项 `resource:action` 权限。
- 绑定：admin 拥有全部权限；member 授「读 + 基础写」10 项
  （5 项 read + task:create/task:update + comment:create +
  attachment:upload/download）。

幂等性：全部 INSERT 带 `ON CONFLICT DO NOTHING`——重放或部分执行后
再次升级都不会因 UNIQUE 冲突中断。降级只删除种子引入的行（按 name /
按种子角色名定位），不触碰运行期产生的数据。

开发文档 §56 Phase 4 验收要求 ADMIN / MEMBER「权限表现不同」，
本迁移即该验收的数据前提。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0de65c197efc'
down_revision: Union[str, None] = '7e15047d3a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 开发文档 §6「权限示例」完整清单（22 项，resource:action 格式）。
ALL_PERMISSIONS: list[str] = [
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
]

# member 的「读 + 基础写」子集（TASK-022 决策）。
MEMBER_PERMISSIONS: list[str] = [
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
]


def _insert_roles() -> None:
    op.execute(
        """
        INSERT INTO roles (name, description)
        VALUES
            ('admin',  'Administrator - full access to all resources'),
            ('member', 'Regular member - read access plus basic write operations')
        ON CONFLICT (name) DO NOTHING
        """
    )


def _insert_permissions() -> None:
    values = ",\n".join(f"('{name}')" for name in ALL_PERMISSIONS)
    op.execute(
        f"""
        INSERT INTO permissions (name)
        VALUES
            {values}
        ON CONFLICT (name) DO NOTHING
        """
    )


def _bind_permissions(role: str, permission_names: list[str]) -> None:
    values = ",\n".join(f"('{name}')" for name in permission_names)
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.name IN ({values})
        WHERE r.name = '{role}'
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )


def upgrade() -> None:
    _insert_roles()
    _insert_permissions()
    _bind_permissions("admin", ALL_PERMISSIONS)
    _bind_permissions("member", MEMBER_PERMISSIONS)


def downgrade() -> None:
    # 只移除种子授予的绑定与种子角色/权限本身；
    # role_permissions / user_roles 依赖 role 行的级联删除兜底清理关联。
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING roles r
        WHERE rp.role_id = r.id AND r.name IN ('admin', 'member')
        """
    )
    op.execute(
        """
        DELETE FROM user_roles ur
        USING roles r
        WHERE ur.role_id = r.id AND r.name IN ('admin', 'member')
        """
    )
    op.execute("DELETE FROM roles WHERE name IN ('admin', 'member')")
    values = ", ".join(f"('{name}')" for name in ALL_PERMISSIONS)
    op.execute(f"DELETE FROM permissions WHERE name IN ({values})")
