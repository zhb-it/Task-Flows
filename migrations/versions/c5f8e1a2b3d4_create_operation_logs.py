"""create_operation_logs

Revision ID: c5f8e1a2b3d4
Revises: b90b4cff0f64
Create Date: 2026-09-14 09:10:00.000000

TASK-039 操作审计日志表（源文档 §15）。user_id 按决策不加外键；
payload 用 JSONB + GIN 索引；落 (resource_type, resource_id) 与
(user_id, created_at DESC) 两个 B-tree 索引。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


# revision identifiers, used by Alembic.
revision: str = 'c5f8e1a2b3d4'
down_revision: Union[str, None] = 'b90b4cff0f64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'operation_logs',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column(
            'payload',
            pg.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_operation_logs_resource',
        'operation_logs',
        ['resource_type', 'resource_id'],
        unique=False,
    )
    op.create_index(
        'ix_operation_logs_user_created',
        'operation_logs',
        ['user_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_operation_logs_payload',
        'operation_logs',
        ['payload'],
        unique=False,
        postgresql_using='gin',
    )


def downgrade() -> None:
    op.drop_index('ix_operation_logs_payload', table_name='operation_logs')
    op.drop_index('ix_operation_logs_user_created', table_name='operation_logs')
    op.drop_index('ix_operation_logs_resource', table_name='operation_logs')
    op.drop_table('operation_logs')
