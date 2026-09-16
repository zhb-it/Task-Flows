"""README / 面试文档护栏（TASK-063）。

## 为什么需要

README 是仓库的门面，也是**最容易悄悄说谎**的文档：它描述的是「项目现在长什么样」，
而项目一直在变。TASK-064 已为 `PROGRESS.md ↔ TASKS.md` 建了护栏，本文件把
README 与面试文档纳入同一套机制。

## 与 `scripts/check_docs.py` 的分工

- `scripts/check_docs.py` 是**人的入口**：提交前一条命令，只读文本与文件系统，
  不连数据库、不上网，因此可以随时跑；
- 本文件是 **CI 门禁**，并且能做检查器做不到的事：导入 app，取真实的 OpenAPI 契约与
  ORM `metadata`，把 README 里「16 张业务表 / 20 条外键 / 40 个操作」这类结构性声明
  与**代码事实**对齐——而不只是与另一份文档对齐（两份文档可以一起错）。

## 反向用例不是可选项

下面每条规则都配了一个用**合成输入**把它弄坏的用例。没有这一层，一个「永远返回空
列表」的检查器也能让「仓库一致」那条断言通过——这正是本项目在别处踩过的假绿。
"""

from __future__ import annotations

import re
from pathlib import Path

from app.db.base import Base
from app.main import app
from scripts.check_docs import (
    MIGRATION_COUNT_RE,
    PROJECT_ROOT,
    TEST_FILE_COUNT_RE,
    check,
    check_interview_text,
    check_readme_text,
    check_repo_facts,
)

README_PATH = PROJECT_ROOT / "README.md"
INTERVIEW_PATH = PROJECT_ROOT / "docs" / "INTERVIEW.md"
SPEC_PATH = PROJECT_ROOT / "团队任务协作系统_项目开发文档.md"
QUALITY_PATH = PROJECT_ROOT / "docs" / "QUALITY.md"
TASKS_PATH = PROJECT_ROOT / "docs" / "TASKS.md"
PROGRESS_PATH = PROJECT_ROOT / "docs" / "PROGRESS.md"

README_TEXT = README_PATH.read_text(encoding="utf-8")
INTERVIEW_TEXT = INTERVIEW_PATH.read_text(encoding="utf-8")
SPEC_TEXT = SPEC_PATH.read_text(encoding="utf-8")
QUALITY_TEXT = QUALITY_PATH.read_text(encoding="utf-8")
TASKS_TEXT = TASKS_PATH.read_text(encoding="utf-8")
PROGRESS_TEXT = PROGRESS_PATH.read_text(encoding="utf-8")

#: README 目录树里声明的模块数：`(目录, 声明的正则)`。
#: 正则在 README 里**必须能匹配到**——匹配不到即视为失败，否则改写措辞就能让检查
#: 静默失效（那是「假绿」的另一种形态）。
DIRECTORY_COUNT_RULES: tuple[tuple[str, str, str], ...] = (
    ("app/api/v1", r"Router 层（(?P<num>\d+)\s*个模块", "Router 层"),
    ("app/crud", r"(?P<num>\d+)\s*个数据访问模块", "数据访问模块"),
    ("app/models", r"(?P<num>\d+)\s*个模型模块", "模型模块"),
    ("app/schemas", r"(?P<num>\d+)\s*个请求响应模型模块", "请求响应模型模块"),
    ("app/services", r"(?P<num>\d+)\s*个业务服务", "业务服务"),
)


# --- 合成样例：用于反向用例（不依赖仓库真实内容，改坏了也不会误伤仓库） --------------

SYNTH_SPEC = """# 项目开发文档

## Phase 17：README 与面试

README 必须包含：

```text
项目介绍
技术栈
```

---

# 56. 面试重点

项目完成后必须能够独立解释以下问题：

## FastAPI

1. FastAPI 为什么适合这个项目？

## Redis

2. Redis 为什么适合做限流？

---

# 57. 项目最终验收标准
"""

SYNTH_TASKS = """# Tasks

## Phase 10：工程化
- [x] TASK-001 骨架
- [x] TASK-002 依赖
- [ ] TASK-003 登录
"""

SYNTH_PROGRESS = """# Progress

## Current Phase
Phase 10：工程化

## Current Task
TASK-002 依赖

## Completed
- [x] TASK-001 骨架
- [x] TASK-002 依赖

## Next
TASK-003 登录
"""

SYNTH_README = """# 项目

> 当前处于 Phase 10（工程化），TASK-001 ~ TASK-002 全部交付。

## 项目介绍

内容。

## 技术栈

内容。

## 测试

> **当前基线（快照 2026-01-01）**：100 passed，0 failed。

## 文档

内容。
"""

SYNTH_QUALITY = """# 质量基线

> **当前基线（快照 2026-01-01）**：100 passed / 2 个测试文件。
"""

SYNTH_INTERVIEW = """# 面试技术难点

## FastAPI

### 1. FastAPI 为什么适合这个项目？

答。

## Redis

### 2. Redis 为什么适合做限流？

答。
"""


def _synth_readme_problems(
    readme: str = SYNTH_README,
    quality: str = SYNTH_QUALITY,
    spec: str = SYNTH_SPEC,
    tasks: str = SYNTH_TASKS,
    progress: str = SYNTH_PROGRESS,
) -> list[str]:
    return check_readme_text(readme, spec, tasks, progress, quality)


# --- 1. 守护仓库现状（CI 门禁的实际落点） ----------------------------------------


def test_repository_documents_pass_every_rule() -> None:
    """README / INTERVIEW / PROGRESS / TASKS / 数量声明全部规则在真实仓库上必须通过。"""
    problems = check()
    assert problems == [], (
        "文档之间出现了矛盾（README / 面试文档 / 进度文档）：\n"
        + "\n".join(f"  - {problem}" for problem in problems)
        + "\n\n本地可直接复现：python scripts/check_docs.py"
    )


def test_readme_declares_the_frontier_reported_by_tasks() -> None:
    """README 的「已交付到 TASK-NNN」不能与 TASKS.md 的勾选前沿脱节。"""
    match = re.search(r"TASK-\d+\s*~\s*TASK-(\d+)\s*全部交付", README_TEXT)
    assert match is not None, "README 里没有「TASK-001 ~ TASK-NNN 全部交付」声明"

    done = [
        int(number)
        for number in re.findall(r"^- \[x\] TASK-(\d+)", TASKS_TEXT, re.M)
        if number
    ]
    assert int(match.group(1)) == max(done)


#: README 里「没有任何未完成任务」的措辞——有未勾选任务时它就是一句谎话。
_NO_PENDING_CLAIM_RE = re.compile(r"无未完成任务")


def test_readme_does_not_claim_completion_while_tasks_are_pending() -> None:
    """TASKS.md 里有未勾选任务时，README 不许声称「无未完成任务」。

    TASK-087 收尾时这里的断言方向是反的（断言「未勾选任务必须为空」）。项目随后进入
    Phase 18 企业化规划（`docs/ENTERPRISE_READINESS.md`），未勾选任务变成**计划**
    而不是**遗漏**，于是这件事由 `scripts/check_docs.py` 的第 6 条不变量接管——
    它保证勾选编号是 `1..max` 的连续区间，因此「已交付到 TASK-NNN」这句话仍然可信，
    而本用例守住 README 不出现在同一段里自相矛盾的声明。

    正向那半（README 声明的前沿必须等于 TASKS.md 的勾选前沿）在
    `test_readme_declares_the_frontier_reported_by_tasks` 里，不受 pending 影响。
    """
    pending = re.findall(r"^- \[ \] TASK-(\d+)", TASKS_TEXT, re.M)

    if pending:
        assert not _NO_PENDING_CLAIM_RE.search(README_TEXT), (
            f"docs/TASKS.md 里有 {len(pending)} 个未勾选任务，"
            "但 README 声称「无未完成任务」——前沿声明因此不成立"
        )


# --- 2. README 的结构性声明必须与代码事实一致 --------------------------------------


def test_readme_table_count_matches_the_orm_metadata() -> None:
    declared = {int(number) for number in re.findall(r"(\d+)\s*张业务表", README_TEXT)}

    assert declared, "README 里没有「N 张业务表」声明"
    assert declared == {len(Base.metadata.tables)}, (
        f"README 声明 {sorted(declared)} 张业务表，"
        f"ORM metadata 里实际有 {len(Base.metadata.tables)} 张"
    )


def test_readme_foreign_key_count_matches_the_orm_metadata() -> None:
    declared = {int(number) for number in re.findall(r"(\d+)\s*条外键", README_TEXT)}
    actual = sum(len(table.foreign_key_constraints) for table in Base.metadata.tables.values())

    assert declared, "README 里没有「N 条外键」声明"
    assert declared == {actual}, f"README 声明 {sorted(declared)} 条外键，实际 {actual} 条"


def test_readme_constraint_counts_match_the_orm_metadata() -> None:
    unique = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    checks = [
        constraint
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if constraint.__class__.__name__ == "CheckConstraint"
    ]

    declared_unique = {int(number) for number in re.findall(r"(\d+)\s*个唯一约束", README_TEXT)}
    declared_checks = {int(number) for number in re.findall(r"(\d+)\s*个\s*CHECK", README_TEXT)}

    assert declared_unique == {len(unique)}, (
        f"README 声明 {sorted(declared_unique)} 个唯一约束，实际 {len(unique)} 个"
    )
    assert declared_checks == {len(checks)}, (
        f"README 声明 {sorted(declared_checks)} 个 CHECK，实际 {len(checks)} 个"
    )


def test_readme_operation_count_matches_the_openapi_schema() -> None:
    operations = [
        (path, method)
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in ("get", "post", "patch", "put", "delete")
    ]
    declared = {int(number) for number in re.findall(r"(\d+)\s*个操作", README_TEXT)}

    assert declared, "README 里没有「N 个操作」声明"
    assert declared == {len(operations)}, (
        f"README 声明 {sorted(declared)} 个操作，OpenAPI 里实际 {len(operations)} 个"
    )


def test_readme_api_path_count_matches_the_openapi_schema() -> None:
    versioned = {path for path in app.openapi()["paths"] if path.startswith("/api/v1")}
    declared = {
        int(number) for number in re.findall(r"共\s*(\d+)\s*条\s*`/api/v1`\s*路径", README_TEXT)
    }

    assert declared, "README 里没有「共 N 条 `/api/v1` 路径」声明"
    assert declared == {len(versioned)}, (
        f"README 声明 {sorted(declared)} 条 `/api/v1` 路径，实际 {len(versioned)} 条"
    )


def test_readme_module_counts_match_the_filesystem() -> None:
    """目录树里「N 个模块」的说法必须与目录下真实的模块文件数一致。"""
    for directory, pattern, label in DIRECTORY_COUNT_RULES:
        match = re.search(pattern, README_TEXT)
        assert match is not None, (
            f"README 里找不到「{label}」的数量声明（正则 {pattern!r}）——"
            "改写措辞会让这条检查静默失效，请同步更新本测试"
        )
        modules = [
            path
            for path in (PROJECT_ROOT / directory).glob("*.py")
            if path.name != "__init__.py"
        ]
        assert int(match.group("num")) == len(modules), (
            f"README 声明 {directory} 有 {match.group('num')} 个模块，实际 {len(modules)} 个"
        )


def test_every_relative_markdown_link_in_the_readme_resolves() -> None:
    """README 里的相对链接必须指向真实存在的文件（防止文档重命名后链接腐烂）。"""
    broken: list[str] = []
    for target in re.findall(r"\[[^\]]*\]\((?P<target>[^)]+)\)", README_TEXT):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (PROJECT_ROOT / target.split("#", 1)[0]).resolve()
        if not path.exists():
            broken.append(target)

    assert broken == [], f"README 里有指向不存在文件的链接：{broken}"


# --- 3. 面试文档必须逐条覆盖 §56 --------------------------------------------------


def test_interview_document_covers_every_spec_question() -> None:
    """32 条答案 + 3 条漏答看起来都一样「有内容」，所以必须逐条比对题号与题干。"""
    spec_questions = dict(
        (int(number), text)
        for number, text in re.findall(
            r"^(\d+)\.\s+(.+?)\s*$",
            SPEC_TEXT.split("# 56. 面试重点", 1)[1].split("\n# 57", 1)[0],
            re.M,
        )
    )
    answered = dict(
        (int(number), text)
        for number, text in re.findall(r"^###\s+(\d+)\.\s+(.+?)\s*$", INTERVIEW_TEXT, re.M)
    )

    assert spec_questions, "未能从开发文档 §56 解析出问题清单"
    assert sorted(answered) == sorted(spec_questions), (
        "面试文档的题号与 §56 不一致："
        f"漏答 {sorted(set(spec_questions) - set(answered))}，"
        f"多出 {sorted(set(answered) - set(spec_questions))}"
    )
    for number in sorted(spec_questions):
        assert answered[number] == spec_questions[number], (
            f"题 {number} 的题干与 §56 不逐字一致："
            f"规格 {spec_questions[number]!r} / 本文 {answered[number]!r}"
        )


# --- 4. 反向用例：每条规则都必须能真的报出问题 --------------------------------------


def test_synthetic_documents_are_accepted_first() -> None:
    """反向用例的前提：合成样例本身必须自洽，否则下面的断言证明不了任何事。"""
    assert _synth_readme_problems() == []
    assert check_interview_text(SYNTH_INTERVIEW, SYNTH_SPEC) == []


def test_missing_required_readme_section_is_detected() -> None:
    broken = SYNTH_README.replace("## 技术栈\n\n内容。\n\n", "")

    problems = _synth_readme_problems(broken)

    assert any("缺少规格 §Phase 17 要求的部分" in problem for problem in problems), problems


def test_baseline_mismatch_between_readme_and_quality_is_detected() -> None:
    broken = SYNTH_QUALITY.replace("100 passed", "101 passed")

    problems = _synth_readme_problems(quality=broken)

    assert any("两处必须一致" in problem for problem in problems), problems


def test_readme_without_a_baseline_declaration_is_detected() -> None:
    broken = SYNTH_README.replace("**当前基线（快照 2026-01-01）**", "**某次跑的**")

    problems = _synth_readme_problems(broken)

    assert any("README.md 里没有" in problem for problem in problems), problems


def test_quality_without_a_baseline_declaration_is_detected() -> None:
    problems = _synth_readme_problems(quality="# 质量基线\n\n没有基线声明。\n")

    assert any("docs/QUALITY.md 里没有" in problem for problem in problems), problems


def test_readme_phase_drift_against_progress_is_detected() -> None:
    broken = SYNTH_README.replace("Phase 10（工程化）", "Phase 9（通知）")

    problems = _synth_readme_problems(broken)

    assert any("README.md 声明处于 Phase 9" in problem for problem in problems), problems


def test_readme_frontier_behind_tasks_is_detected() -> None:
    broken = SYNTH_README.replace("TASK-001 ~ TASK-002", "TASK-001 ~ TASK-001")

    problems = _synth_readme_problems(broken)

    assert any("已交付到 TASK-001" in problem for problem in problems), problems


def test_readme_without_a_frontier_declaration_is_detected() -> None:
    broken = SYNTH_README.replace("TASK-001 ~ TASK-002 全部交付", "进行中")

    problems = _synth_readme_problems(broken)

    assert any("进度前沿声明" in problem for problem in problems), problems


def test_unparseable_spec_is_reported_instead_of_silently_passing() -> None:
    """规格解析失败必须报出来——否则「解析不到」会伪装成「全都对」。"""
    problems = _synth_readme_problems(spec="# 项目开发文档\n\n没有任何清单。\n")

    assert any("规格解析失败" in problem for problem in problems), problems

    assert check_interview_text(SYNTH_INTERVIEW, "# 没有第 56 节\n") != []


def test_missing_interview_domain_is_detected() -> None:
    broken = SYNTH_INTERVIEW.replace("## Redis\n\n### 2.", "## 其它\n\n### 2.")

    problems = check_interview_text(broken, SYNTH_SPEC)

    assert any("缺少领域章节" in problem for problem in problems), problems


def test_missing_interview_answer_is_detected() -> None:
    broken = SYNTH_INTERVIEW.replace(
        "### 2. Redis 为什么适合做限流？\n\n答。\n", ""
    )

    problems = check_interview_text(broken, SYNTH_SPEC)

    assert any("漏答" in problem for problem in problems), problems


def test_paraphrased_interview_question_is_detected() -> None:
    """题干被改写（「像是回答了但其实答的是另一个问题」）必须报出来。"""
    broken = SYNTH_INTERVIEW.replace(
        "### 2. Redis 为什么适合做限流？", "### 2. Redis 有什么优点？"
    )

    problems = check_interview_text(broken, SYNTH_SPEC)

    assert any("不逐字一致" in problem for problem in problems), problems


def test_wrong_migration_count_in_readme_is_detected() -> None:
    broken = re.sub(r"\d+\s*个\s*(?:Alembic\s*)?迁移", "999 个迁移", README_TEXT, count=1)

    problems = check_repo_facts(broken)

    assert any("个迁移" in problem for problem in problems), problems


def test_wrong_test_file_count_in_readme_is_detected() -> None:
    broken = re.sub(r"\d+\s*个\s*测试文件", "999 个测试文件", README_TEXT, count=1)

    problems = check_repo_facts(broken)

    assert any("个测试文件" in problem for problem in problems), problems


def test_readme_still_states_the_counts_this_file_checks() -> None:
    """README 必须继续声明这些数量——改掉措辞就等于悄悄关掉检查。

    迁移与测试文件这两条直接复用检查器的正则对象（而不是在这里重写一份），
    否则正则一旦分叉，「仍在声明」与「真的在检查」就会各说各话。
    """
    for pattern in (
        MIGRATION_COUNT_RE,
        TEST_FILE_COUNT_RE,
        r"\d+\s*张业务表",
        r"\d+\s*条外键",
        r"\d+\s*个唯一约束",
        r"\d+\s*个\s*CHECK",
        r"\d+\s*个操作",
        r"共\s*\d+\s*条\s*`/api/v1`\s*路径",
    ):
        assert re.search(pattern, README_TEXT), f"README 里不再有匹配 {pattern!r} 的声明"


def test_readme_links_are_relative_to_the_repository_root() -> None:
    """本文件的链接检查以仓库根为基准，README 也必须放在仓库根。"""
    assert README_PATH.parent == Path(PROJECT_ROOT)
    assert INTERVIEW_PATH.parent == Path(PROJECT_ROOT) / "docs"
