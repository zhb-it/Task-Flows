"""任务搜索索引与全文检索列（TASK-064；开发文档 §14 / §57）。

## 这个文件在守护什么

开发文档 §57 的数据库能力清单列了 `pg_trgm`，`docs/DB_SCHEMA.md` 另列了 `tsvector`
（「任务标题+描述全文搜索」）。TASK-062 的质量检查发现**两者都不存在**——`keyword`
搜索走的是 `title ILIKE '%x%'`，而 `ILIKE` 的非锚定模式**用不了 B-tree 索引**，
执行计划是顺序扫描，性能随 `tasks` 行数线性劣化。TASK-064 补上：

    CREATE EXTENSION pg_trgm
    tasks.search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,''))
    ) STORED
    GIN (search_vector)          -- 全文检索
    GIN (title gin_trgm_ops)     -- 模糊匹配（让 ILIKE '%x%' 走索引）

本文件用三层断言把它钉住（**离线层 + 落库层 + 执行计划层**）：

1. **离线层**：Model 上的生成表达式与两个 GIN 索引声明正确，且生成列不会被应用写入；
2. **落库层**：扩展真的装了、列真的是 `tsvector` + `is_generated='ALWAYS'`、两个索引
   真的是 GIN 且带 `gin_trgm_ops`；
3. **执行计划层**：`ILIKE '%x%'` 与 `search_vector @@ tsquery` **真的能用到各自索引**
   ——这是「性能修复名副其实」的唯一硬证据（光有索引定义不代表优化器会用）。

## 一个刻意的设计边界（有测试固化）

`keyword` 查询**保持** `title ILIKE`（`app/crud/task.py`），**没有**改写到
`search_vector` 上。原因是 `to_tsvector('simple')` **不做中文分词**：实测
`'修复登录缺陷'` 会成为**单个 token**，于是 `to_tsquery('simple','登录')` 匹配不到它。
而 pg_trgm 按三字符组切分、与语言无关，中文子串检索照常有效。所以「中文场景下
trgm 索引 + ILIKE」才是可用的组合，tsvector 列作为 §14 声明的能力落库但**不参与
keyword 查询**（见 DECISIONS 045 与 docs/QUALITY.md D5）。

## 操作注意事项

- `EXPLAIN` 前一律 `SET LOCAL enable_seqscan = off`。本测试库 `tasks` 表通常只有个位数
  行，这种规模下优化器**必然**选择顺序扫描，直接 EXPLAIN 会得到「索引没被用」的
  **假阴性**。排除顺序扫描后看到的是「索引对该查询形状可用」——这才是索引的意义所在；
  真实数据量下选不选它是成本决策，不是结构问题。
- 编译查询用 **asyncpg dialect** 而非 psycopg2 dialect：后者的 paramstyle 会把
  `%login%` 转义成 `%%login%%`（在 `text()` 里不会还原），虽然双写通配符恰好等价、
  但会让断言与被测 SQL 对不上号。

零残留：RUN_TOKEN 前缀 + autouse teardown 精确删除（tasks → projects → teams → users）。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import asyncpg as asyncpg_dialect
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.crud.task import list_tasks_by_project
from app.models.project import Project
from app.models.task import SEARCH_VECTOR_SQL, Task
from app.models.team import Team
from app.models.user import User

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/taskflow"

RUN_TOKEN = uuid.uuid4().hex[:10]

engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)

#: 用于验证「子串模糊匹配」的英文标题（trigram 对 ASCII 按字符切分）。
ASCII_TITLE = f"Fix Login Bug {RUN_TOKEN}"
#: 用于验证「中文子串」的标题——`('simple')` 不分词，整串会成为单一 token。
CHINESE_TITLE = f"修复登录缺陷 {RUN_TOKEN}"
#: 描述里的关键词，用来证明 `search_vector` 确实把 description 也纳入（§14 原文）。
DESCRIPTION_MARKER = "keyboard"
DESCRIPTION = f"Reproduce with a {DESCRIPTION_MARKER} only"


# --- 夹具 --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def _cleanup():
    yield
    async with SessionFactory() as session:
        await session.execute(
            delete(Task).where(Task.title.like(f"%{RUN_TOKEN}%"))
        )
        await session.execute(
            delete(Project).where(Project.name.like(f"%{RUN_TOKEN}%"))
        )
        await session.execute(delete(Team).where(Team.name.like(f"%{RUN_TOKEN}%")))
        await session.execute(
            delete(User).where(User.username.like(f"%{RUN_TOKEN}%"))
        )
        await session.commit()


async def _seed(tasks: list[tuple[str, str | None]]) -> tuple[int, list[Task]]:
    """建一条 user → team → project 链并插入给定任务，返回 (project_id, tasks)。"""
    async with SessionFactory() as session:
        user = User(
            username=f"tasksearch_{RUN_TOKEN}",
            email=f"tasksearch_{RUN_TOKEN}@example.com",
            password_hash="h",
        )
        session.add(user)
        await session.flush()

        team = Team(name=f"tasksearch team {RUN_TOKEN}", owner_id=user.id)
        session.add(team)
        await session.flush()

        project = Project(
            name=f"tasksearch proj {RUN_TOKEN}",
            team_id=team.id,
            owner_id=user.id,
        )
        session.add(project)
        await session.flush()

        created = [
            Task(
                project_id=project.id,
                title=title,
                description=description,
                creator_id=user.id,
            )
            for title, description in tasks
        ]
        session.add_all(created)
        await session.commit()
        return project.id, created


async def _search_vector_of(task_id: int) -> str:
    """直接读 DB 里那一列（不走 ORM 属性，因为它是 DB 端生成的）。"""
    async with SessionFactory() as session:
        return await session.scalar(
            text("SELECT search_vector::text FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        )


async def _explain(stmt) -> str:
    """返回查询在「禁用顺序扫描」下的执行计划文本（理由见模块 docstring）。"""
    literal = str(
        stmt.compile(
            dialect=asyncpg_dialect.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    async with SessionFactory() as session:
        await session.execute(text("SET LOCAL enable_seqscan = off"))
        rows = (await session.execute(text(f"EXPLAIN {literal}"))).all()
    return "\n".join(row[0] for row in rows)


# --- 1. 离线层：Model 声明 --------------------------------------------------------


def test_search_vector_is_a_stored_generated_column():
    """§14：生成列必须是 `GENERATED ALWAYS AS (...) STORED`，而不是应用维护的普通列。"""
    column = Task.__table__.columns["search_vector"]
    assert column.computed is not None, "search_vector 必须是 DB 生成列"
    assert column.computed.persisted is True, "生成列必须 STORED（VIRTUAL 无法建 GIN 索引）"

    expression = str(column.computed.sqltext)
    assert "to_tsvector('simple'" in expression
    assert "coalesce(title" in expression
    assert "coalesce(description" in expression, "§14 要求 title + description 都纳入"


def test_search_vector_expression_matches_the_spec():
    """表达式是这套搜索能力的数据来源，改动它必须同步改动本断言（防止静默漂移）。"""
    assert SEARCH_VECTOR_SQL == (
        "to_tsvector('simple', "
        "coalesce(title, '') || ' ' || coalesce(description, ''))"
    )


def test_generated_column_is_omitted_from_application_inserts():
    """生成列由 DB 计算，应用侧 INSERT 不得带上它。

    若带上，PostgreSQL 会直接拒绝（`cannot insert a non-DEFAULT value into column`），
    所以这条断言保护的是「DB 端生成」这个前提本身。
    """
    compiled = str(
        insert(Task)
        .values(title="x", project_id=1, creator_id=1)
        .compile(dialect=asyncpg_dialect.dialect())
    )
    assert "search_vector" not in compiled


def test_model_declares_both_gin_search_indexes():
    """两个索引声明在 Model 上，autogenerate 才不会把它们当成「库里多出来的东西」。"""
    indexes = {index.name: index for index in Task.__table__.indexes}

    trgm = indexes["ix_tasks_title_trgm"]
    assert [column.name for column in trgm.columns] == ["title"]
    assert trgm.dialect_options["postgresql"]["using"] == "gin"
    assert trgm.dialect_options["postgresql"]["ops"]["title"] == "gin_trgm_ops"

    fulltext = indexes["ix_tasks_search_vector"]
    assert [column.name for column in fulltext.columns] == ["search_vector"]
    assert fulltext.dialect_options["postgresql"]["using"] == "gin"


# --- 2. 落库层：真实数据库形态 ----------------------------------------------------


async def test_pg_trgm_extension_is_installed():
    """§57 清单项之一：扩展必须真的装上了（`gin_trgm_ops` 由它提供）。"""
    async with SessionFactory() as session:
        version = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'pg_trgm'")
        )
    assert version is not None, "pg_trgm 扩展未安装"


async def test_search_vector_column_is_a_tsvector_generated_always():
    async with SessionFactory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT data_type, is_generated, generation_expression "
                    "FROM information_schema.columns "
                    "WHERE table_name = 'tasks' AND column_name = 'search_vector'"
                )
            )
        ).one_or_none()

    assert row is not None, "tasks.search_vector 列不存在"
    data_type, is_generated, expression = row
    assert data_type == "tsvector"
    assert is_generated == "ALWAYS"
    assert "to_tsvector" in expression


async def test_gin_indexes_exist_in_the_database():
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'tasks'"
                )
            )
        ).all()
    definitions = {name: definition for name, definition in rows}

    assert "USING gin (search_vector)" in definitions["ix_tasks_search_vector"]
    assert "gin_trgm_ops" in definitions["ix_tasks_title_trgm"]


async def test_database_fills_search_vector_without_application_code():
    """插一条任务，`search_vector` 由 DB 自动填好，且 title 与 description 都在里面。

    这条同时是「应用不写生成列」的运行时证据：若 ORM 把该列写进 INSERT，
    PostgreSQL 会报错，本用例直接失败。
    """
    _, tasks = await _seed([(ASCII_TITLE, DESCRIPTION)])

    vector = await _search_vector_of(tasks[0].id)

    assert vector is not None
    assert "login" in vector, f"title 未进入 search_vector: {vector!r}"
    assert DESCRIPTION_MARKER in vector, f"description 未进入 search_vector: {vector!r}"


async def test_search_vector_follows_title_updates():
    """生成列随行更新自动重算——不需要任何 Service 层代码去同步它。"""
    _, tasks = await _seed([("placeholder title", None)])
    task_id = tasks[0].id

    async with SessionFactory() as session:
        await session.execute(
            text("UPDATE tasks SET title = :title WHERE id = :task_id"),
            {"title": f"renamed to zebra {RUN_TOKEN}", "task_id": task_id},
        )
        await session.commit()

    vector = await _search_vector_of(task_id)
    assert "zebra" in vector
    assert "placeholder" not in vector


# --- 3. 执行计划层：索引真的被用上 -------------------------------------------------


async def test_ilike_substring_query_can_use_the_trigram_index():
    """本 TASK 的核心收益：`keyword` 的 `ILIKE '%x%'` 从顺序扫描变成索引扫描。

    这正是 `ILIKE` 单独存在时的痛点——非锚定模式用不了 B-tree，只能顺序扫描；
    pg_trgm 的 trigram GIN 索引让它可以走 `Bitmap Index Scan`。
    """
    await _seed([(ASCII_TITLE, None)])

    plan = await _explain(select(Task.id).where(Task.title.ilike("%login%")))

    assert "ix_tasks_title_trgm" in plan, f"ILIKE 未用上 trgm 索引:\n{plan}"


async def test_ilike_can_use_the_trigram_index_for_chinese_too():
    """pg_trgm 按字符组切分、与语言无关，所以中文子串同样用得上该索引。

    这是「中文场景选 trgm 而不是 tsvector」的直接依据（另一个依据见下一个用例）。
    """
    await _seed([(CHINESE_TITLE, None)])

    plan = await _explain(select(Task.id).where(Task.title.ilike("%登录缺陷%")))

    assert "ix_tasks_title_trgm" in plan, f"中文 ILIKE 未用上 trgm 索引:\n{plan}"


async def test_full_text_query_can_use_the_gin_index():
    """§57 的 tsvector 能力必须真能用：`search_vector @@ tsquery` 走 GIN 索引。"""
    await _seed([(ASCII_TITLE, DESCRIPTION)])

    plan = await _explain(
        select(Task.id).where(
            text("search_vector @@ to_tsquery('simple', 'keyboard')")
        )
    )

    assert "ix_tasks_search_vector" in plan, f"全文检索未用上 GIN 索引:\n{plan}"


async def test_chinese_substring_matches_ilike_but_not_the_full_text_index():
    """固化「keyword 继续走 ILIKE」这个决定的依据，防止将来有人顺手改到 tsvector。

    `to_tsvector('simple')` 不做中文分词：`修复登录缺陷` 会成为**单个 token**，
    因此 `to_tsquery('simple','登录')` 匹配不到它（子串查询无解）；
    而 `ILIKE '%登录%'` 正常命中。若把 keyword 改到 search_vector 上，
    中文检索会**静默失效**——所以这里把两种行为同时断言下来。
    """
    project_id, _ = await _seed([(CHINESE_TITLE, None)])

    async with SessionFactory() as session:
        ilike_hits = (
            await session.execute(
                text(
                    "SELECT count(*) FROM tasks "
                    "WHERE project_id = :project_id AND title ILIKE :pattern"
                ),
                {"project_id": project_id, "pattern": "%登录%"},
            )
        ).scalar_one()

        tsquery_hits = (
            await session.execute(
                text(
                    "SELECT count(*) FROM tasks "
                    "WHERE project_id = :project_id "
                    "AND search_vector @@ to_tsquery('simple', '登录')"
                ),
                {"project_id": project_id},
            )
        ).scalar_one()

    assert ilike_hits == 1, "中文子串应当被 ILIKE 命中"
    assert tsquery_hits == 0, (
        "`simple` 配置不分中文词——若这里变成 1，说明分词行为变了，"
        "需要重新评估 keyword 是否可以改走 search_vector"
    )


# --- 4. 语义未变：keyword 仍是大小写不敏感子串 ------------------------------------


async def test_keyword_filter_still_matches_substrings_case_insensitively():
    """本 TASK 只加索引、**不改查询语义**：keyword 仍是标题的大小写不敏感子串匹配。

    直接调 CRUD 层（`list_tasks_by_project`），因为 ILIKE 就是在那里拼进 SQL 的；
    接口层的 keyword 契约由 `tests/test_task_query_api.py`（TASK-035）覆盖。
    """
    project_id, _ = await _seed(
        [(ASCII_TITLE, None), (f"Unrelated chore {RUN_TOKEN}", None)]
    )

    async with SessionFactory() as session:
        hits = await list_tasks_by_project(session, project_id, keyword="%LOGIN%")

    assert [task.title for task in hits] == [ASCII_TITLE], (
        "keyword 应当大小写不敏感地子串匹配标题，且只命中一条"
    )
