"""create_comments

Revision ID: d7a3b9c1e5f2
Revises: c5f8e1a2b3d4
Create Date: 2026-09-14 10:05:00.000000

TASK-041 评论表（源文档 §16）。task_id / user_id 双 FK ON DELETE CASCADE；
(task_id, created_at) 复合索引；user_id 单列索引。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7a3b9c1e5f2'
down_revision: Union[str, None] = 'c5f8e1a2b3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comments',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_comments_user_id', 'comments', ['user_id'], unique=False)
    op.create_index(
        'ix_comments_task_id_created_at',
        'comments',
        ['task_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_comments_task_id_created_at', table_name='comments')
    op.drop_index('ix_comments_user_id', table_name='comments')
    op.drop_table('comments')
