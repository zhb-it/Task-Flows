#!/usr/bin/env python
"""文档一致性检查（TASK-064 建立，TASK-063 扩展到 README / 面试文档）。

检查三组不变量：

1. `docs/PROGRESS.md` ↔ `docs/TASKS.md`（进度摘要与任务事实源）
2. `README.md` ↔ 规格 / 进度 / 质量基线（README 是仓库门面，最容易悄悄说谎）
3. `docs/INTERVIEW.md` ↔ 开发文档 §56（35 个必答问题一个都不能少）

---

## 为什么需要这个东西

本项目已**四次**（TASK-048 / 049 / 051 / 062）出现同一类事故：收尾时回写
`docs/PROGRESS.md`，编辑动作报告「成功」，但**内容并没有真的落盘**——典型表现是
`## Current Task` 更新对了，而 `## Completed` 的勾选行与 `## Next` 停在上一轮。
两次是提交后人工核验才发现的（TASK-048 那次直到 TASK-049 才被顺带修正）。

靠「记得逐行核验」是不行的：核验需要人主动想起来，而这类缺失**不报错、不影响测试**，
唯一的表现是文档悄悄地说谎。所以把「核验」变成一条可执行命令：

    python scripts/check_docs.py

退出码 0 = 一致；非 0 = 打印每一处具体的矛盾。同一条逻辑被
`tests/test_docs_consistency.py` 复用，因此 **CI 的 pytest 会自动拦住**，
带病提交无法合入。

## 检查的不变量

`docs/TASKS.md` 是任务的**事实来源**（哪些任务存在、勾选状态、属于哪个 Phase），
`docs/PROGRESS.md` 是它的**摘要**。摘要必须与事实一致：

1. `## Current Task` 行以 `TASK-NNN` 开头，且该任务在 TASKS.md 中存在并**已勾选**；
2. `## Completed` 的 `- [x] TASK-NNN` 列表与 TASKS.md 已勾选任务**集合与顺序都相同**；
3. `## Completed` 的**最后一条**就是 `## Current Task`（这条正是历史事故的落点：
   Completed 停在 N-1 而 Current Task 已经写成 N）；
4. `## Next` 行以 `TASK-NNN` 开头，且指向 TASKS.md 中**第一个未勾选**任务；
5. `## Current Phase` 与 Current Task 在 TASKS.md 里所属的 Phase 标题一致。

第 3 条是「静默丢失」的直接探针；第 2 条能抓住更隐蔽的情况（只补了 Current Task
和 Next、忘了往 Completed 里追加一行）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_PATH = PROJECT_ROOT / "docs" / "TASKS.md"
PROGRESS_PATH = PROJECT_ROOT / "docs" / "PROGRESS.md"
README_PATH = PROJECT_ROOT / "README.md"
INTERVIEW_PATH = PROJECT_ROOT / "docs" / "INTERVIEW.md"
QUALITY_PATH = PROJECT_ROOT / "docs" / "QUALITY.md"
#: 原始开发文档（规格事实来源）。
SPEC_PATH = PROJECT_ROOT / "团队任务协作系统_项目开发文档.md"

_PHASE_RE = re.compile(r"^##\s+(Phase\s+.*)$")
_TASKS_ITEM_RE = re.compile(r"^-\s+\[(?P<mark>[ xX])\]\s+TASK-(?P<num>\d+)")
_PROGRESS_DONE_RE = re.compile(r"^-\s+\[x\]\s+TASK-(?P<num>\d+)")
_LEADING_TASK_RE = re.compile(r"^TASK-(?P<num>\d+)")

# --- README / 面试文档相关 -------------------------------------------------

#: 规格 §Phase 17 引出「README 必须包含」的那一行（其后是一个 ```text 代码块）。
_README_SPEC_ANCHOR = "README 必须包含"
#: §56 面试重点的标题（其后到下一个一级标题之间是 35 个问题）。
_INTERVIEW_SPEC_ANCHOR = "# 56. 面试重点"
#: README 里「当前处于 Phase N」的声明。容忍 markdown 强调与全/半角冒号。
_README_PHASE_RE = re.compile(r"当前(?:处于|进度)[：:]?\s*\**\s*Phase\s+(?P<num>\d+)")
#: 任意文档里 `N passed` 的声明（用于 README ↔ QUALITY 的基线互校）。
_PASSED_RE = re.compile(r"(?P<num>\d+)\s*passed")
#: markdown 行内链接 `[文案](目标)`。
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((?P<target>[^)]+)\)")
#: 一级标题（用于界定 §56 的结束）。
_H1_RE = re.compile(r"^#\s+")
#: 二级 / 三级标题（README 的章节名、面试文档的题号标题）。
_H2_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_H3_RE = re.compile(r"^###\s+(?P<num>\d+)\.\s+(?P<text>.+?)\s*$")
#: 编号问题 `1. xxx`。
_NUMBERED_RE = re.compile(r"^(?P<num>\d+)\.\s+(?P<text>.+?)\s*$")
#: `Phase N` 里的编号（PROGRESS 的 Phase 标题带中文后缀，故只比编号）。
_PHASE_NUM_RE = re.compile(r"Phase\s+(?P<num>\d+)")
#: 基线声明的标记词。README 与 QUALITY 都必须有一行带它的、写着 `N passed` 的声明。
_BASELINE_MARKER = "当前基线"
_BASELINE_RE = re.compile(r"当前基线[^\n]*?(?P<num>\d+)\s*passed")
#: README 里「TASK-001 ~ TASK-NNN 全部交付」这句（N 是已交付的任务前沿）。
_FRONTIER_RE = re.compile(r"TASK-\d+\s*~\s*TASK-(?P<hi>\d+)\s*全部交付")
#: README 里可被文件系统直接推翻的数量声明。
#: 这两个模式刻意保持简单；若某天 README 需要用同一句式表达**另一种**数量
#: （例如「3 个测试文件的 teardown 有问题」并不是总数），请改写措辞而不是把这个
#: 正则复杂化——复杂到看不懂的护栏等于没有护栏。`(?!的)` 是为这个真实歧义留的。
#:
#: 公开（无前导下划线）是**有意**的：`tests/test_readme.py` 会直接断言这两个模式
#: 在 README 里仍能匹配到，否则改写措辞就能让数量检查静默失效。
MIGRATION_COUNT_RE = re.compile(r"(?P<num>\d+)\s*个\s*(?:Alembic\s*)?迁移")
TEST_FILE_COUNT_RE = re.compile(r"(?P<num>\d+)\s*个\s*测试文件(?!的)")


class Task(NamedTuple):
    number: int
    done: bool
    phase: str


def parse_tasks(text: str) -> list[Task]:
    """按出现顺序解析 TASKS.md 的 `- [x] TASK-NNN` 条目及其所属 Phase。"""
    tasks: list[Task] = []
    phase = ""
    for raw in text.splitlines():
        line = raw.strip()
        phase_match = _PHASE_RE.match(line)
        if phase_match:
            phase = phase_match.group(1).strip()
            continue
        item = _TASKS_ITEM_RE.match(line)
        if item:
            tasks.append(
                Task(
                    number=int(item.group("num")),
                    done=item.group("mark").lower() == "x",
                    phase=phase,
                )
            )
    return tasks


def parse_progress_sections(text: str) -> dict[str, list[str]]:
    """把 PROGRESS.md 切成 `{章节名: 正文行}`（标题行本身不含在内）。"""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def _first_line(lines: list[str]) -> str:
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def check_text(tasks_text: str, progress_text: str) -> list[str]:
    """返回问题列表（空列表 = 一致）。纯函数，便于用合成文本验证检查器本身。"""
    problems: list[str] = []

    tasks = parse_tasks(tasks_text)
    if not tasks:
        return ["docs/TASKS.md 里没有解析到任何 `- [x] TASK-NNN` 条目"]

    by_number = {task.number: task for task in tasks}
    done_order = [task.number for task in tasks if task.done]
    pending = [task.number for task in tasks if not task.done]

    sections = parse_progress_sections(progress_text)
    for required in ("Current Phase", "Current Task", "Completed", "Next"):
        if required not in sections:
            problems.append(f"docs/PROGRESS.md 缺少章节 `## {required}`")
    if problems:
        return problems

    # --- 1/2. Current Task 必须是一个已勾选的真实任务 ---------------------------
    current_line = _first_line(sections["Current Task"])
    current_match = _LEADING_TASK_RE.match(current_line)
    if not current_match:
        problems.append(
            f"`## Current Task` 必须以 `TASK-NNN` 开头，实际是：{current_line!r}"
        )
        current_number = None
    else:
        current_number = int(current_match.group("num"))
        if current_number not in by_number:
            problems.append(
                f"`## Current Task` 指向 TASK-{current_number:03d}，"
                "但 docs/TASKS.md 中不存在该任务"
            )
        elif not by_number[current_number].done:
            problems.append(
                f"`## Current Task` 指向 TASK-{current_number:03d}，"
                "但它在 docs/TASKS.md 中仍是未勾选状态"
            )

    # --- 3. Completed 列表必须与 TASKS.md 的勾选集合、顺序都一致 ----------------
    progress_done = [
        int(match.group("num"))
        for line in sections["Completed"]
        for match in [_PROGRESS_DONE_RE.match(line.strip())]
        if match
    ]
    if progress_done != done_order:
        missing = sorted(set(done_order) - set(progress_done))
        extra = sorted(set(progress_done) - set(done_order))
        problems.append(
            "`## Completed` 与 docs/TASKS.md 的已勾选任务不一致\n"
            f"    TASKS.md 已勾选 {len(done_order)} 项、PROGRESS 列出 {len(progress_done)} 项\n"
            f"    漏写：{missing or '无'}\n"
            f"    多写：{extra or '无'}\n"
            f"    顺序一致：{progress_done == sorted(progress_done)}"
        )

    # --- 4. Completed 末行必须是 Current Task（历史事故的直接探针） -------------
    if progress_done and current_number is not None:
        if progress_done[-1] != current_number:
            problems.append(
                f"`## Completed` 的最后一条是 TASK-{progress_done[-1]:03d}，"
                f"而 `## Current Task` 是 TASK-{current_number:03d}"
                "——通常是完成一个 TASK 后忘了往 Completed 追加，"
                "或 Current Task 被提前改了"
            )

    # --- 5. Next 必须是第一个未勾选任务（全做完时则不许再指向任何 TASK） --------
    next_line = _first_line(sections["Next"])
    next_match = _LEADING_TASK_RE.match(next_line)
    if pending:
        if not next_match:
            problems.append(f"`## Next` 必须以 `TASK-NNN` 开头，实际是：{next_line!r}")
        else:
            next_number = int(next_match.group("num"))
            if next_number != pending[0]:
                problems.append(
                    f"`## Next` 指向 TASK-{next_number:03d}，"
                    f"但 docs/TASKS.md 中第一个未勾选任务是 TASK-{pending[0]:03d}"
                )
    elif next_match:
        # 任务全部勾完（例如 TASK-063 收尾后）：`## Next` 若还停在某个 TASK 上，
        # 说明「全部完成」这件事没人写下来，读者会以为还有活没干。
        problems.append(
            f"docs/TASKS.md 中已没有未勾选任务，但 `## Next` 仍指向 "
            f"TASK-{int(next_match.group('num')):03d}——应改为显式声明「全部完成」"
        )

    # --- 6. Current Phase 必须与 Current Task 的 Phase 一致 --------------------
    if current_number is not None and current_number in by_number:
        expected_phase = by_number[current_number].phase
        actual_phase = _first_line(sections["Current Phase"])
        if expected_phase and actual_phase != expected_phase:
            problems.append(
                f"`## Current Phase` 是 {actual_phase!r}，"
                f"但 TASK-{current_number:03d} 在 docs/TASKS.md 中属于 {expected_phase!r}"
            )

    return problems


# --- README / 面试文档：与规格和事实源的一致性 ------------------------------


def parse_required_readme_sections(spec_text: str) -> list[str]:
    """取开发文档 §Phase 17「README 必须包含」之后那个 ```text 代码块里的部分名。"""
    lines = spec_text.splitlines()
    anchor = next(
        (index for index, line in enumerate(lines) if _README_SPEC_ANCHOR in line), None
    )
    if anchor is None:
        return []
    sections: list[str] = []
    inside = False
    for line in lines[anchor:]:
        stripped = line.strip()
        if stripped.startswith("```"):
            if inside:
                break
            inside = True
            continue
        if inside and stripped:
            sections.append(stripped)
    return sections


def parse_h2_titles(text: str) -> list[str]:
    """全部 `## ` 标题的正文（保持出现顺序）。"""
    return [
        match.group("title")
        for line in text.splitlines()
        for match in [_H2_RE.match(line.strip())]
        if match
    ]


def parse_spec_interview(spec_text: str) -> tuple[list[str], dict[int, str]]:
    """取开发文档 §56 的（领域顺序, {题号: 题干}）。§56 到下一个一级标题为止。"""
    lines = spec_text.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if line.strip() == _INTERVIEW_SPEC_ANCHOR),
        None,
    )
    if start is None:
        return [], {}
    end = next(
        (index for index in range(start + 1, len(lines)) if _H1_RE.match(lines[index])),
        len(lines),
    )
    domains: list[str] = []
    questions: dict[int, str] = {}
    for line in lines[start:end]:
        stripped = line.strip()
        heading = _H2_RE.match(stripped)
        if heading:
            domains.append(heading.group("title"))
            continue
        numbered = _NUMBERED_RE.match(stripped)
        if numbered:
            questions[int(numbered.group("num"))] = numbered.group("text")
    return domains, questions


def parse_interview_answers(interview_text: str) -> tuple[list[str], dict[int, str]]:
    """面试文档的（`##` 领域顺序, {题号: 题干}）。题干取自 `### N. …` 标题。"""
    domains: list[str] = []
    answers: dict[int, str] = {}
    for line in interview_text.splitlines():
        stripped = line.strip()
        heading = _H2_RE.match(stripped)
        if heading:
            domains.append(heading.group("title"))
            continue
        question = _H3_RE.match(stripped)
        if question:
            answers[int(question.group("num"))] = question.group("text")
    return domains, answers


def _declared_baseline(text: str) -> int | None:
    match = _BASELINE_RE.search(text)
    return int(match.group("num")) if match else None


def check_readme_text(
    readme_text: str,
    spec_text: str,
    tasks_text: str,
    progress_text: str,
    quality_text: str,
) -> list[str]:
    """README ↔ 规格 / TASKS / PROGRESS / QUALITY 的交叉校验。纯函数，便于合成验证。"""
    problems: list[str] = []

    # --- 1. 规格 §Phase 17 列出的部分一个都不能少 ------------------------------
    required = parse_required_readme_sections(spec_text)
    if not required:
        problems.append(
            f"开发文档里找不到 {_README_SPEC_ANCHOR!r} 及其后的清单——"
            "规格解析失败，完整性无法校验"
        )
    else:
        present = set(parse_h2_titles(readme_text))
        missing = [name for name in required if name not in present]
        if missing:
            problems.append(
                f"README.md 缺少规格 §Phase 17 要求的部分 "
                f"（缺 {len(missing)}/{len(required)}）：" + "、".join(missing)
            )

    # --- 2. 基线数字必须与 QUALITY.md 一致 ------------------------------------
    readme_baseline = _declared_baseline(readme_text)
    quality_baseline = _declared_baseline(quality_text)
    if readme_baseline is None:
        problems.append(
            f"README.md 里没有 `{_BASELINE_MARKER}…：N passed` 形式的基线声明"
        )
    if quality_baseline is None:
        problems.append(
            f"docs/QUALITY.md 里没有 `{_BASELINE_MARKER}…：N passed` 形式的基线声明"
        )
    if (
        readme_baseline is not None
        and quality_baseline is not None
        and readme_baseline != quality_baseline
    ):
        problems.append(
            f"README.md 声明的基线是 {readme_baseline} passed，"
            f"docs/QUALITY.md 声明的是 {quality_baseline} passed——两处必须一致"
        )

    # --- 3. README 声明的 Phase 必须与 PROGRESS 的 Current Phase 一致 ----------
    sections = parse_progress_sections(progress_text)
    progress_phase_line = _first_line(sections.get("Current Phase", []))
    progress_phase = (
        int(match.group("num")) if (match := _PHASE_NUM_RE.search(progress_phase_line)) else None
    )
    phase_match = _README_PHASE_RE.search(readme_text)
    readme_phase = int(phase_match.group("num")) if phase_match else None
    if readme_phase is None:
        problems.append("README.md 里没有声明当前 Phase（形如「当前处于 Phase 10」）")
    elif progress_phase is None:
        problems.append(
            f"docs/PROGRESS.md 的 `## Current Phase` 里解析不到 Phase 编号："
            f"{progress_phase_line!r}"
        )
    elif readme_phase != progress_phase:
        problems.append(
            f"README.md 声明处于 Phase {readme_phase}，"
            f"但 docs/PROGRESS.md 的 `## Current Phase` 是 {progress_phase_line!r}"
        )

    # --- 4. README 的「已交付到 TASK-NNN」必须等于 TASKS.md 的已勾选前沿 --------
    frontier_match = _FRONTIER_RE.search(readme_text)
    done_numbers = [task.number for task in parse_tasks(tasks_text) if task.done]
    if frontier_match is None:
        problems.append(
            "README.md 里没有「TASK-001 ~ TASK-NNN 全部交付」形式的进度前沿声明"
        )
    elif done_numbers:
        frontier = int(frontier_match.group("hi"))
        if frontier != max(done_numbers):
            problems.append(
                f"README.md 声明已交付到 TASK-{frontier:03d}，"
                f"但 docs/TASKS.md 中已勾选的最大编号是 TASK-{max(done_numbers):03d}"
            )

    return problems


def check_interview_text(interview_text: str, spec_text: str) -> list[str]:
    """面试文档必须逐条覆盖规格 §56 的 9 个领域、35 个问题。纯函数。"""
    spec_domains, spec_questions = parse_spec_interview(spec_text)
    if not spec_domains or not spec_questions:
        return [
            f"开发文档里找不到 {_INTERVIEW_SPEC_ANCHOR!r} 下的领域与问题——"
            "规格解析失败，覆盖率无法校验"
        ]

    problems: list[str] = []
    domains, answers = parse_interview_answers(interview_text)

    missing_domains = [domain for domain in spec_domains if domain not in domains]
    if missing_domains:
        problems.append(
            "docs/INTERVIEW.md 缺少领域章节：" + "、".join(missing_domains)
        )

    missing = [number for number in sorted(spec_questions) if number not in answers]
    if missing:
        problems.append(
            f"docs/INTERVIEW.md 漏答 {len(missing)}/{len(spec_questions)} 个问题："
            f"题号 {missing}"
        )

    mismatched = [
        number
        for number in sorted(spec_questions)
        if number in answers and answers[number] != spec_questions[number]
    ]
    if mismatched:
        preview = "\n".join(
            f"    题 {number}：规格 {spec_questions[number]!r} / 本文 {answers[number]!r}"
            for number in mismatched[:5]
        )
        problems.append(
            f"docs/INTERVIEW.md 有 {len(mismatched)} 个题干与规格 §56 不逐字一致"
            "（题干必须照抄：改写会让「其实是另一个问题」蒙混过去）：\n" + preview
        )

    return problems


def check_repo_facts(readme_text: str, repo_root: Path = PROJECT_ROOT) -> list[str]:
    """README 里那些「用文件系统一查就知道真假」的数量声明。"""
    problems: list[str] = []

    actual_migrations = len(list((repo_root / "migrations" / "versions").glob("*.py")))
    for number in sorted(
        {int(match.group("num")) for match in MIGRATION_COUNT_RE.finditer(readme_text)}
    ):
        if number != actual_migrations:
            problems.append(
                f"README.md 声明「{number} 个迁移」，但 migrations/versions 下"
                f"实际有 {actual_migrations} 个迁移文件"
            )

    actual_test_files = len(list((repo_root / "tests").glob("test_*.py")))
    for number in sorted(
        {int(match.group("num")) for match in TEST_FILE_COUNT_RE.finditer(readme_text)}
    ):
        if number != actual_test_files:
            problems.append(
                f"README.md 声明「{number} 个测试文件」，但 tests/ 下"
                f"实际有 {actual_test_files} 个 test_*.py"
            )

    return problems


def check(
    tasks_path: Path = TASKS_PATH, progress_path: Path = PROGRESS_PATH
) -> list[str]:
    """读取真实文件并检查（路径可覆盖，便于测试）。"""
    required = (tasks_path, progress_path, README_PATH, INTERVIEW_PATH, SPEC_PATH, QUALITY_PATH)
    for path in required:
        if not path.exists():
            return [f"缺少文件：{path}"]

    problems = check_text(
        tasks_path.read_text(encoding="utf-8"),
        progress_path.read_text(encoding="utf-8"),
    )
    problems += check_readme_text(
        README_PATH.read_text(encoding="utf-8"),
        SPEC_PATH.read_text(encoding="utf-8"),
        tasks_path.read_text(encoding="utf-8"),
        progress_path.read_text(encoding="utf-8"),
        QUALITY_PATH.read_text(encoding="utf-8"),
    )
    problems += check_interview_text(
        INTERVIEW_PATH.read_text(encoding="utf-8"),
        SPEC_PATH.read_text(encoding="utf-8"),
    )
    problems += check_repo_facts(README_PATH.read_text(encoding="utf-8"))
    return problems


def main() -> int:
    problems = check()
    if not problems:
        print(
            "文档一致：docs/PROGRESS.md ↔ docs/TASKS.md、README.md ↔ "
            "规格/进度/质量基线、docs/INTERVIEW.md ↔ 规格 §56，数量声明 ↔ 文件系统。"
        )
        return 0
    print("文档之间出现了矛盾：\n")
    for index, problem in enumerate(problems, start=1):
        print(f"  [{index}] {problem}\n")
    print("修好后重跑：python scripts/check_docs.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
