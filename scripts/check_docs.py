#!/usr/bin/env python
"""进度文档一致性检查（TASK-064）。

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

_PHASE_RE = re.compile(r"^##\s+(Phase\s+.*)$")
_TASKS_ITEM_RE = re.compile(r"^-\s+\[(?P<mark>[ xX])\]\s+TASK-(?P<num>\d+)")
_PROGRESS_DONE_RE = re.compile(r"^-\s+\[x\]\s+TASK-(?P<num>\d+)")
_LEADING_TASK_RE = re.compile(r"^TASK-(?P<num>\d+)")


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

    # --- 5. Next 必须是第一个未勾选任务 ----------------------------------------
    next_line = _first_line(sections["Next"])
    next_match = _LEADING_TASK_RE.match(next_line)
    if not next_match:
        problems.append(f"`## Next` 必须以 `TASK-NNN` 开头，实际是：{next_line!r}")
    elif pending:
        next_number = int(next_match.group("num"))
        if next_number != pending[0]:
            problems.append(
                f"`## Next` 指向 TASK-{next_number:03d}，"
                f"但 docs/TASKS.md 中第一个未勾选任务是 TASK-{pending[0]:03d}"
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


def check(
    tasks_path: Path = TASKS_PATH, progress_path: Path = PROGRESS_PATH
) -> list[str]:
    """读取真实文件并检查（路径可覆盖，便于测试）。"""
    for path in (tasks_path, progress_path):
        if not path.exists():
            return [f"缺少文件：{path}"]
    return check_text(
        tasks_path.read_text(encoding="utf-8"),
        progress_path.read_text(encoding="utf-8"),
    )


def main() -> int:
    problems = check()
    if not problems:
        print("docs/TASKS.md 与 docs/PROGRESS.md 一致。")
        return 0
    print("docs/PROGRESS.md 与 docs/TASKS.md 不一致：\n")
    for index, problem in enumerate(problems, start=1):
        print(f"  [{index}] {problem}\n")
    print("修好后重跑：python scripts/check_docs.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
