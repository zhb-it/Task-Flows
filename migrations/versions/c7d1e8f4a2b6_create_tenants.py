"""create tenants table + seed tenant:manage permission (TASK-093)

TASK-093 租户模型与生命周期（开发文档 §61.3 多租户）：

1. ``tenants`` 表：id / name / slug / status / member_limit /
   storage_limit_bytes / created_at / updated_at。列定稿见
   docs/DB_SCHEMA.md「tenants（TASK-093）」，决策登记 docs/DECISIONS.md 065：
   - slug 全局 UNIQUE + CHECK 格式（对外标识，创建后不可变）；
   - status 值域 CHECK（转换白名单由 Service 执行，DB 表达不了「从哪来」）；
   - 配额列可空，NULL = 未设限。
2. 种子：新增权限 ``tenant:manage`` 并授予全局 ``admin`` 角色。这是
   「平台管理员」能力的先行表达——租户内角色（TASK-096 落地）永不持有它。
   幂等写法沿用 0de65c197efc 种子迁移的 ON CONFLICT DO NOTHING 惯例。

降级：先删种子绑定与权限行，再 drop 表（表内无被引用关系，drop 无顺序约束）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d1e8f4a2b6'
down_revision: Union[str, None] = 'e3a7c1f9b2d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_MANAGE_PERMISSION = "tenant:manage"


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('slug', sa.String(length=63), nullable=False),
        sa.Column(
            'status',
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column('member_limit', sa.Integer(), nullable=True),
        sa.Column('storage_limit_bytes', sa.BigInteger(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug', name='uq_tenants_slug'),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name='ck_tenants_status',
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$'",
            name='ck_tenants_slug_format',
        ),
        sa.CheckConstraint(
            'member_limit IS NULL OR member_limit > 0',
            name='ck_tenants_member_limit',
        ),
        sa.CheckConstraint(
            'storage_limit_bytes IS NULL OR storage_limit_bytes >= 0',
            name='ck_tenants_storage_limit',
        ),
    )

    # 平台管理员能力面（DECISIONS 065）：tenant:manage 只授予全局 admin。
    op.execute(
        f"""
        INSERT INTO permissions (name)
        VALUES ('{TENANT_MANAGE_PERMISSION}')
        ON CONFLICT (name) DO NOTHING
        """
    )
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.name = '{TENANT_MANAGE_PERMISSION}'
        WHERE r.name = 'admin'
        ON CONFLICT (role_id, permission_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name = '{TENANT_MANAGE_PERMISSION}'
        )
        """
    )
    op.execute(
        f"DELETE FROM permissions WHERE name = '{TENANT_MANAGE_PERMISSION}'"
    )
    op.drop_table('tenants')
