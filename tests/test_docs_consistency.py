"""进度文档一致性护栏（TASK-064）。

## 背景

`docs/PROGRESS.md` 的收尾回写已**四次**出现「编辑报成功但内容没落盘」（TASK-048 /
049 / 051 / 062），表现是 `## Current Task` 更新了、而 `## Completed` 与 `## Next`
停在上一轮。这类缺失**不报错、不影响任何测试**——唯一的表现是文档悄悄说谎，
提交后没人重看就永久错了（TASK-048 那次直到 TASK-049 才被顺带修正）。

所以本文件把「核验」变成 CI 会自动执行的断言：只要
`docs/PROGRESS.md` 与 `docs/TASKS.md` 出现矛盾，pytest 就红。

## 两层

1. **守护仓库现状**：真实文件必须一致（`test_repository_docs_are_consistent`）；
2. **证明护栏不是空转**：下面用**合成文档**构造每一种历史/可能的矛盾，断言检查器
   真的会报出来。没有这一层，一个「永远返回空列表」的假检查器也能让第 1 层通过——
   那正是本项目在别处踩过的「假绿」。
"""

from __future__ import annotations

from pathlib import Path

from scripts.check_docs import PROJECT_ROOT, check_text

REPO_TASKS = PROJECT_ROOT / "docs" / "TASKS.md"
REPO_PROGRESS = PROJECT_ROOT / "docs" / "PROGRESS.md"

#: 一份**自洽**的最小样例（用于下面所有反向用例的基线）。
CONSISTENT_TASKS = """# Tasks

## Phase 1：基础设施
- [x] TASK-001 骨架
- [x] TASK-002 依赖

## Phase 2：认证
- [ ] TASK-003 登录
"""

CONSISTENT_PROGRESS = """# Progress

## Current Phase
Phase 1：基础设施

## Current Task
TASK-002 依赖

## Completed
- [x] TASK-001 骨架
- [x] TASK-002 依赖

## Next
TASK-003 登录
"""


def _problems(progress_text: str) -> list[str]:
    return check_text(CONSISTENT_TASKS, progress_text)


def _replace(progress_text: str, old: str, new: str) -> str:
    assert old in progress_text, f"样例文档里没有 {old!r}"
    return progress_text.replace(old, new, 1)


# --- 1. 守护仓库现状（CI 门禁的实际落点） ----------------------------------------


def test_repository_docs_are_consistent() -> None:
    """仓库里真实的 PROGRESS.md 必须与 TASKS.md 一致；不一致时打印全部矛盾点。

    只断言 TASKS/PROGRESS 这一组（`check_text`），README / 面试文档那几组在
    `tests/test_readme.py` 里断言——那里会调用覆盖全部规则的 `check()`。
    """
    problems = check_text(
        REPO_TASKS.read_text(encoding="utf-8"),
        REPO_PROGRESS.read_text(encoding="utf-8"),
    )
    assert problems == [], (
        "docs/PROGRESS.md 与 docs/TASKS.md 不一致（通常是回写文档时内容没落盘）：\n"
        + "\n".join(f"  - {problem}" for problem in problems)
        + "\n\n本地可直接复现：python scripts/check_docs.py"
    )


def test_checker_reads_the_real_document_paths() -> None:
    """检查器指向的确实是仓库里的那两个文件（防止路径写错导致「检查了个寂寞」）。"""
    assert REPO_TASKS.parent == PROJECT_ROOT / "docs"
    assert REPO_PROGRESS.name == "PROGRESS.md"
    assert Path(REPO_TASKS).exists()
    assert Path(REPO_PROGRESS).exists()


# --- 2. 基线：自洽样例必须通过 ---------------------------------------------------


def test_consistent_documents_produce_no_problems() -> None:
    assert _problems(CONSISTENT_PROGRESS) == []


# --- 3. 反向用例：每一种矛盾都必须被抓到 ------------------------------------------


def test_stale_completed_list_is_detected() -> None:
    """TASK-062 事故的原形：Current Task 已推进，Completed 少最后一条。"""
    stale = _replace(CONSISTENT_PROGRESS, "- [x] TASK-002 依赖\n", "")

    problems = _problems(stale)

    assert any("Completed" in problem for problem in problems), problems


def test_completed_missing_a_middle_entry_is_detected() -> None:
    """更隐蔽的情况：只补了 Current Task / Next，忘了往 Completed 追加中间的条目。"""
    stale = _replace(CONSISTENT_PROGRESS, "- [x] TASK-001 骨架\n", "")

    problems = _problems(stale)

    assert any("漏写" in problem for problem in problems), problems


def test_next_pointing_at_a_finished_task_is_detected() -> None:
    """TASK-062 事故的另一半：Completed 停在 N-1 时，`## Next` 也还指着 N。"""
    stale = _replace(CONSISTENT_PROGRESS, "## Next\nTASK-003 登录", "## Next\nTASK-002 依赖")

    problems = _problems(stale)

    assert any("Next" in problem for problem in problems), problems


def test_current_phase_mismatch_is_detected() -> None:
    stale = _replace(CONSISTENT_PROGRESS, "Phase 1：基础设施", "Phase 2：认证")

    problems = _problems(stale)

    assert any("Current Phase" in problem for problem in problems), problems


def test_current_task_that_is_still_unchecked_is_detected() -> None:
    stale = _replace(
        CONSISTENT_PROGRESS,
        "## Current Task\nTASK-002 依赖",
        "## Current Task\nTASK-003 登录",
    )

    problems = _problems(stale)

    assert any("未勾选" in problem for problem in problems), problems


def test_current_task_that_does_not_exist_is_detected() -> None:
    stale = _replace(
        CONSISTENT_PROGRESS,
        "## Current Task\nTASK-002 依赖",
        "## Current Task\nTASK-099 不存在的任务",
    )

    problems = _problems(stale)

    assert any("不存在" in problem for problem in problems), problems


def test_section_line_not_starting_with_a_task_number_is_detected() -> None:
    """章节内容被写成整句叙述（丢了 `TASK-NNN` 前缀）也要报出来。"""
    stale = _replace(
        CONSISTENT_PROGRESS,
        "## Next\nTASK-003 登录",
        "## Next\n下一个任务是登录功能",
    )

    problems = _problems(stale)

    assert any("必须以 `TASK-NNN` 开头" in problem for problem in problems), problems


def test_missing_section_is_detected() -> None:
    stale = _replace(CONSISTENT_PROGRESS, "## Next\nTASK-003 登录\n", "")

    problems = _problems(stale)

    assert any("缺少章节" in problem for problem in problems), problems


def test_empty_tasks_document_is_reported() -> None:
    """文档结构被改坏（解析不出任务条目）不能静默通过。"""
    problems = check_text("# Tasks\n\n暂时没有任务\n", CONSISTENT_PROGRESS)

    assert problems == ["docs/TASKS.md 里没有解析到任何 `- [x] TASK-NNN` 条目"]


#: 一份**全部任务已完成**的样例（TASK-063 收尾后的形态：`## Next` 不再指向任何 TASK）。
ALL_DONE_TASKS = CONSISTENT_TASKS.replace("- [ ] TASK-003 登录", "- [x] TASK-003 登录")

ALL_DONE_PROGRESS = """# Progress

## Current Phase
Phase 2：认证

## Current Task
TASK-003 登录

## Completed
- [x] TASK-001 骨架
- [x] TASK-002 依赖
- [x] TASK-003 登录

## Next
无——全部任务已完成
"""


def test_next_still_naming_a_task_after_everything_is_done_is_detected() -> None:
    """全部任务勾完后 `## Next` 若还停在某个 TASK 上，要报出来。

    这是 TASK-063 收尾时才会走到的分支（`pending` 为空）：若不处理，「已经做完了」
    这件事就没人写下来，而检查器会静默通过——正是本文件要防的那类假绿。
    """
    progress = _replace(ALL_DONE_PROGRESS, "无——全部任务已完成", "TASK-003 登录")

    problems = check_text(ALL_DONE_TASKS, progress)

    assert any("已没有未勾选任务" in problem for problem in problems), problems


def test_next_declaring_completion_is_accepted() -> None:
    """与之配套的正向用例：显式声明「全部完成」时不得报错。"""
    assert check_text(ALL_DONE_TASKS, ALL_DONE_PROGRESS) == []
