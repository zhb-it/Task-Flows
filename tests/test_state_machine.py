"""TASK-037 状态机规则测试（纯离线，不依赖数据库）。

覆盖矩阵：合法前进链、非终态 → CANCELLED、终态完全封死、同状态
重复流转、跨级跳转、ConflictError 文案与状态码、allowed_targets 白名单。
"""

import pytest

from app.core.exceptions import ConflictError
from app.models.task import TaskStatus
from app.services.state_machine import (
    INVALID_TRANSITION,
    TERMINAL_STATUSES,
    TRANSITIONS,
    allowed_targets,
    can_transition,
    validate_transition,
)

S = TaskStatus


class TestTransitionTable:
    def test_table_covers_all_statuses(self):
        assert set(TRANSITIONS) == set(TaskStatus)

    def test_terminal_statuses(self):
        assert TERMINAL_STATUSES == {S.DONE, S.CANCELLED}


class TestLegalTransitions:
    """合法：严格前进链 + 非终态 → CANCELLED。"""

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (S.TODO, S.IN_PROGRESS),
            (S.IN_PROGRESS, S.REVIEW),
            (S.REVIEW, S.DONE),
            # 非终态任意 → CANCELLED
            (S.TODO, S.CANCELLED),
            (S.IN_PROGRESS, S.CANCELLED),
            (S.REVIEW, S.CANCELLED),
        ],
    )
    def test_legal(self, current, target):
        assert can_transition(current, target) is True
        validate_transition(current, target)  # 不抛异常

    def test_allowed_targets_per_state(self):
        assert allowed_targets(S.TODO) == {S.IN_PROGRESS, S.CANCELLED}
        assert allowed_targets(S.IN_PROGRESS) == {S.REVIEW, S.CANCELLED}
        assert allowed_targets(S.REVIEW) == {S.DONE, S.CANCELLED}
        assert allowed_targets(S.DONE) == set()
        assert allowed_targets(S.CANCELLED) == set()


class TestIllegalTransitions:
    @pytest.mark.parametrize(
        ("current", "target"),
        [
            # 相邻回退（决策 1：仅严格前进）
            (S.IN_PROGRESS, S.TODO),
            (S.REVIEW, S.IN_PROGRESS),
            # 跨级跳转
            (S.TODO, S.REVIEW),
            (S.TODO, S.DONE),
            (S.IN_PROGRESS, S.DONE),
            (S.REVIEW, S.TODO),
            # 终态完全封死（决策 2）：含终态 → CANCELLED
            (S.DONE, S.TODO),
            (S.DONE, S.IN_PROGRESS),
            (S.DONE, S.REVIEW),
            (S.DONE, S.CANCELLED),
            (S.CANCELLED, S.TODO),
            (S.CANCELLED, S.IN_PROGRESS),
            (S.CANCELLED, S.REVIEW),
            (S.CANCELLED, S.DONE),
        ],
    )
    def test_illegal_raises_409(self, current, target):
        assert can_transition(current, target) is False
        with pytest.raises(ConflictError) as exc:
            validate_transition(current, target)
        assert exc.value.detail == INVALID_TRANSITION
        assert exc.value.status_code == 409

    @pytest.mark.parametrize("current", list(TaskStatus))
    def test_same_state_is_illegal(self, current):
        """同状态重复流转（TODO→TODO 等）一律非法（决策 3）。"""
        with pytest.raises(ConflictError):
            validate_transition(current, current)


class TestStrInterop:
    """StrEnum 成员即 str：普通字符串按值查表同样可用（防御性）。"""

    def test_plain_str_lookup(self):
        assert can_transition("TODO", "IN_PROGRESS") is True
        assert can_transition("DONE", "CANCELLED") is False
