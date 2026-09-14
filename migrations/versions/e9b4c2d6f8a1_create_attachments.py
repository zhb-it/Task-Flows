"""create_attachments

Revision ID: e9b4c2d6f8a1
Revises: d7a3b9c1e5f2
Create Date: 2026-09-14 11:20:00.000000

TASK-042 附件表（源文档 §17）。task_id / uploader_id 双 FK ON DELETE
CASCADE；(task_id, created_at) 复合索引；storage_path 唯一约束（防同 key
覆盖）；uploader_id 单列索引。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e9b4c2d6f8a1'
down_revision: Union[str, None] = 'd7a3b9c1e5f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'attachments',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('uploader_id', sa.BigInteger(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('content_type', sa.String(length=255), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['uploader_id'], ['users.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_attachments_uploader_id', 'attachments', ['uploader_id'], unique=False
    )
    op.create_index(
        'ix_attachments_storage_path',
        'attachments',
        ['storage_path'],
        unique=True,
    )
    op.create_index(
        'ix_attachments_task_id_created_at',
        'attachments',
        ['task_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_attachments_task_id_created_at', table_name='attachments')
    op.drop_index('ix_attachments_storage_path', table_name='attachments')
    op.drop_index('ix_attachments_uploader_id', table_name='attachments')
    op.drop_table('attachments')
