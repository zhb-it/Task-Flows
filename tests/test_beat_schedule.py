"""TASK-089 — beat_schedule 契约测试（§61 C1 的防回归闸门）.

TASK-050/051 就把两项维护任务写完了，但调度缺位让它们在生产**永远不会
执行**（``app/`` 内 ``beat|crontab|beat_schedule`` 0 命中）。本文件把
「调度必须存在且正确」钉成契约：

1. **登记契约**：两项任务都在 ``beat_schedule`` 里，entry 的 task 名与
   ``maintenance_tasks`` 的任务名常量一致，且能在 Celery App 上解析到
   对应的注册任务（callable 与任务函数名一致）；
2. **时刻语义**：归档是每日 crontab（hour/minute 来自配置），清理是
   每小时 crontab（hour 为 ``*``，minute 来自配置）；默认值错峰——
   清理分钟不与归档时刻重合；
3. **配置可注入**：改 Settings 后 ``build_beat_schedule()`` 跟着变
   （调度间隔经 .env 可配的落点）；
4. **无孤儿条目**：beat_schedule 里登记的每个 task 都已注册（防止
   「调度在投一个不存在的任务」的静默失效）。

全部离线：只读 Celery App 的配置对象与 Settings，不连 Redis/DB。
"""

import pytest
from celery.schedules import crontab

from app.core.config import get_settings
from app.tasks.celery_app import (
    TASK_NAME_ARCHIVE_LOGS,
    TASK_NAME_CLEANUP_ATTACHMENTS,
    build_beat_schedule,
    celery_app,
)
from app.tasks.maintenance_tasks import (
    archive_operation_logs,
    cleanup_expired_attachments,
)


@pytest.fixture()
def beat_schedule() -> dict:
    return celery_app.conf.beat_schedule


# ---------------------------------------------------------------------------
# 1. 登记契约
# ---------------------------------------------------------------------------


def test_both_maintenance_tasks_are_scheduled(beat_schedule: dict) -> None:
    """两项维护任务都必须在 beat_schedule 里——缺任何一个就是 C1 复发。"""
    assert TASK_NAME_ARCHIVE_LOGS in beat_schedule
    assert TASK_NAME_CLEANUP_ATTACHMENTS in beat_schedule


def test_entry_task_names_match_maintenance_constants(beat_schedule: dict) -> None:
    """entry 指向的 task 名必须是 maintenance_tasks 声明的名字（单一事实源）。"""
    assert beat_schedule[TASK_NAME_ARCHIVE_LOGS]["task"] == TASK_NAME_ARCHIVE_LOGS
    assert (
        beat_schedule[TASK_NAME_CLEANUP_ATTACHMENTS]["task"]
        == TASK_NAME_CLEANUP_ATTACHMENTS
    )


@pytest.mark.parametrize(
    ("entry_key", "expected_run_name"),
    [
        (TASK_NAME_ARCHIVE_LOGS, "archive_operation_logs"),
        (TASK_NAME_CLEANUP_ATTACHMENTS, "cleanup_expired_attachments"),
    ],
)
def test_entry_resolves_to_registered_callable(
    beat_schedule: dict, entry_key: str, expected_run_name: str
) -> None:
    """entry 的 task 名必须在 Celery App 上解析到注册任务，且函数名一致——
    「调度在投、worker 没这个任务」是最隐蔽的一类失效。"""
    entry = beat_schedule[entry_key]
    task = celery_app.tasks.get(entry["task"])
    assert task is not None, f"beat_schedule 引用了未注册的任务: {entry['task']}"
    assert callable(task.run)
    assert task.run.__name__ == expected_run_name


def test_scheduled_callables_are_the_imported_task_objects(beat_schedule: dict) -> None:
    """解析到的任务就是本仓库的维护任务（而不是同名撞车的别的东西）。

    ``@celery_app.task`` 返回的是 Proxy，与 ``celery_app.tasks`` 里的真实
    Task 实例不是同一对象，``is`` 比较恒假；Proxy 背后的 ``.run`` 是同一个
    任务函数对象，用它做身份比较。
    """
    registered = celery_app.tasks[beat_schedule[TASK_NAME_ARCHIVE_LOGS]["task"]]
    assert registered.run is archive_operation_logs.run
    registered = celery_app.tasks[beat_schedule[TASK_NAME_CLEANUP_ATTACHMENTS]["task"]]
    assert registered.run is cleanup_expired_attachments.run


def test_beat_schedule_has_no_unregistered_entries(beat_schedule: dict) -> None:
    """反向契约：beat_schedule 不得登记任何未注册的任务名。"""
    unknown = set(beat_schedule) - set(celery_app.tasks)
    assert not unknown, f"beat_schedule 登记了未注册任务: {sorted(unknown)}"


# ---------------------------------------------------------------------------
# 2. 时刻语义
# ---------------------------------------------------------------------------


def test_archive_schedule_is_a_daily_crontab_from_settings(beat_schedule: dict) -> None:
    """归档：每日一次，hour/minute 来自配置（默认错峰到低位时段）。"""
    settings = get_settings()
    schedule = beat_schedule[TASK_NAME_ARCHIVE_LOGS]["schedule"]
    assert isinstance(schedule, crontab)
    # crontab 字段是 cronexp(frozenset)，具体值是单元素集合。
    assert schedule.hour == {settings.archive_schedule_hour}
    assert schedule.minute == {settings.archive_schedule_minute}
    # 每日 = 与「只给 hour/minute」的参照 crontab 逐字段相等——celery 把
    # dom/month/dow 的通配符展开成全集，直接比引用对象最可靠。
    assert schedule == crontab(
        hour=settings.archive_schedule_hour,
        minute=settings.archive_schedule_minute,
    )


def test_cleanup_schedule_is_an_hourly_crontab_from_settings(
    beat_schedule: dict,
) -> None:
    """清理：每小时一次（hour 为 ``*``），minute 来自配置。"""
    settings = get_settings()
    schedule = beat_schedule[TASK_NAME_CLEANUP_ATTACHMENTS]["schedule"]
    assert isinstance(schedule, crontab)
    assert schedule.minute == {settings.cleanup_schedule_minute}
    # crontab(minute=...) 只给 minute：hour 的通配符被展开成 0..23 全集 → 每小时。
    assert schedule.hour == set(range(24))


def test_default_schedules_are_staggered() -> None:
    """默认错峰：清理分钟不得与归档时刻重合（同一瞬间两任务叠加没有收益，
    只会让那一分钟的负载尖峰更陡）。"""
    settings = get_settings()
    assert settings.cleanup_schedule_minute != settings.archive_schedule_minute


def test_schedule_values_are_within_cron_ranges() -> None:
    """非法的 hour/minute 会在 beat 运行期才炸——把校验提前到契约测试。"""
    settings = get_settings()
    assert 0 <= settings.archive_schedule_hour <= 23
    assert 0 <= settings.archive_schedule_minute <= 59
    assert 0 <= settings.cleanup_schedule_minute <= 59


# ---------------------------------------------------------------------------
# 3. 配置可注入
# ---------------------------------------------------------------------------


def test_build_beat_schedule_follows_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """改 Settings 后 build_beat_schedule() 跟着变——.env 覆盖间隔的落点。"""
    monkeypatch.setattr(get_settings(), "archive_schedule_hour", 5, raising=False)
    monkeypatch.setattr(get_settings(), "archive_schedule_minute", 10, raising=False)
    monkeypatch.setattr(get_settings(), "cleanup_schedule_minute", 55, raising=False)

    schedule = build_beat_schedule()

    # 用 celery 自己的相等语义比对（字段展开后应逐值一致）。
    assert schedule[TASK_NAME_ARCHIVE_LOGS]["schedule"] == crontab(hour=5, minute=10)
    assert schedule[TASK_NAME_CLEANUP_ATTACHMENTS]["schedule"] == crontab(minute=55)
