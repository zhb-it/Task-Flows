"""add task search indexes and search vector

Revision ID: 6765bdcfa73e
Revises: 524ab172e659
Create Date: 2026-09-15 22:04:07.493522

TASK-064：落实开发文档 §14「全文搜索」与 §57「数据库能力清单」里的 `pg_trgm` 与
`tsvector`。本迁移由 `--autogenerate` 产出后手工调整（autogenerate 不知道要建扩展）。

## 三个必须写清楚的点

1. **`CREATE EXTENSION` 必须在建索引之前**：`gin_trgm_ops` 这个 operator class 是
   `pg_trgm` 扩展提供的，扩展不存在时 `CREATE INDEX` 直接报
   `operator class "gin_trgm_ops" does not exist`。这里用 `IF NOT EXISTS` 保证
   重复执行（CI 会 `upgrade → downgrade base → upgrade` 跑两遍）幂等。

2. **`to_tsvector` 必须用两参数形式**：`GENERATED ALWAYS AS (...) STORED` 要求表达式
   是 IMMUTABLE，而 `to_tsvector(text)`（单参数，用 `default_text_search_config`）是
   STABLE，会被拒绝；`to_tsvector(regconfig, text)` 才是 IMMUTABLE。这正是 §14 原文
   写 `to_tsvector('simple', ...)` 的原因。`'simple'` 不做词干还原、**不做中文分词**，
   已知边界见 DECISIONS 045。

3. **downgrade 刻意不 `DROP EXTENSION`**（与 `upgrade` 不对称，属有意为之）：
   扩展是**数据库级**对象而不是 `tasks` 表结构的一部分——一次表级回滚不应连带拆掉
   可能被其它对象依赖的全局扩展（`DROP EXTENSION` 在存在依赖时会直接失败）。本迁移
   只回滚自己拥有的东西（1 列 + 2 索引），配合 `IF NOT EXISTS`，`-- 幂等可重放`，
   CI 的表计数可逆性（16→0→16）不受影响。

## 索引命名

沿用本项目既有惯例 `ix_tasks_*`（`ix_tasks_project_id_status` /
`ix_tasks_creator_id` / `ix_tasks_due_at_open`），而不是 §14 示例里的 `idx_tasks_*`。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6765bdcfa73e'
down_revision: Union[str, None] = '524ab172e659'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ① 扩展先行：gin_trgm_ops 由它提供（幂等，可重放）。
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ② 全文检索列：DB 端生成，应用只读（§14 / DB_SCHEMA「PostgreSQL 能力」）。
    op.add_column(
        'tasks',
        sa.Column(
            'search_vector',
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple', "
                "coalesce(title, '') || ' ' || coalesce(description, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )

    # ③ 两个 GIN 索引：search_vector 的全文索引 + title 的 trigram 索引。
    #    title 的非锚定 `ILIKE '%x%'` 无法使用 B-tree（前缀条件才可），
    #    pg_trgm 的 trigram GIN 索引可以支撑它——这是 keyword 搜索不再随数据量
    #    线性劣化的原因，且**不改动查询语义**（keyword 仍是标题 ILIKE，
    #    见 app/crud/task.py::list_tasks_by_project）。
    op.create_index(
        'ix_tasks_search_vector',
        'tasks',
        ['search_vector'],
        unique=False,
        postgresql_using='gin',
    )
    op.create_index(
        'ix_tasks_title_trgm',
        'tasks',
        ['title'],
        unique=False,
        postgresql_using='gin',
        postgresql_ops={'title': 'gin_trgm_ops'},
    )


def downgrade() -> None:
    # 逆序：索引 → 列；扩展保留（理由见模块 docstring 第 3 点）。
    op.drop_index('ix_tasks_title_trgm', table_name='tasks')
    op.drop_index('ix_tasks_search_vector', table_name='tasks')
    op.drop_column('tasks', 'search_vector')
