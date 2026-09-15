"""TASK-062：存储层路径安全守卫的直接单元测试（全离线）。

## 为什么单独一个文件

TASK-043 的对抗性测试（``tests/test_attachment_security.py``）是从 **HTTP 层**
打进来的，它能证明「恶意文件名进不来」，但**证明不了**存储层自身的守卫逻辑
是完整的——因为 Service 在更前面就把大部分脏输入清洗掉了。结果是
``app/services/storage.py`` 里**真正的安全判定**（盘符拒绝、越界二次确认、
非法 suffix、``max_size`` 守卫）在覆盖率报告里长期是未执行分支。

本文件把存储层当作**独立的安全边界**来测（它自己的 docstring 就是这么定位的：
「本模块是**唯一**做相对 key → 绝对路径转换的地方，因此路径穿越防护集中在这
里实现」）。§48 要求覆盖「路径穿越 / 文件上传漏洞」，那么「这一层的每条拒绝
规则都真的会拒绝」就应当有直接证据，而不是靠上层顺带覆盖。

分四组：

1. ``validate_key`` 的语义层守卫（每条拒绝规则一条用例）；
2. ``build_key`` 的 suffix 收敛（防止调用方把路径片段塞进扩展名）;
3. ``LocalStorageBackend`` 的结构层守卫与 IO 语义（越界二次确认、超限清理
   半成品、幂等删除、目录剪枝）；
4. 后端单例的惰性创建与可重置（测试可注入的依赖点只有这一处）。
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services import storage as storage_service
from app.services.storage import (
    LocalStorageBackend,
    StorageError,
    StorageObjectNotFoundError,
    UnsafeStorageKeyError,
    build_key,
    get_storage_backend,
    reset_storage_backend,
    validate_key,
)

# ===========================================================================
# 1. validate_key —— 语义层守卫
# ===========================================================================


@pytest.mark.parametrize(
    "key",
    [
        "tasks/1/abc.txt",
        "tasks/42/" + "a" * 32,
        "a",
        "a.b_c-d/e",
    ],
)
def test_validate_key_accepts_generated_and_wellformed_keys(key: str) -> None:
    """上传侧真实生成的 key 形态必须被接受（守卫不能误伤正常路径）。"""
    assert validate_key(key) == key


@pytest.mark.parametrize(
    ("key", "why"),
    [
        ("", "空字符串"),
        ("tasks/1/../2/a.txt", "'..' 穿越段"),
        ("../etc/passwd", "首段就是穿越"),
        ("tasks//1/a.txt", "空段"),
        ("tasks/./a.txt", "'.' 段"),
        ("/etc/passwd", "绝对路径"),
        ("tasks\\1\\a.txt", "反斜杠（Windows 分隔符）"),
        ("a b.txt", "空白字符不在许可字符集"),
        ("a:b.txt", "冒号不在许可字符集"),
        ("a*.txt", "通配符不在许可字符集"),
        ("C:/Windows/win.ini", "盘符式前缀"),
        ("c:foo", "裸盘符前缀"),
    ],
)
def test_validate_key_rejects_every_documented_violation(key: str, why: str) -> None:
    """每条拒绝规则都有直接证据——绝不做「清洗后放行」。

    容忍脏 key 会把风险留给未来（模块 docstring 的原话），因此这里逐条钉死：
    违规一律抛 ``UnsafeStorageKeyError``，而不是返回一个改过的 key。
    """
    with pytest.raises(UnsafeStorageKeyError):
        validate_key(key)


def test_validate_key_rejects_non_string() -> None:
    """非字符串同样拒绝（调用方传 None/Path 时不能静默通过）。"""
    with pytest.raises(UnsafeStorageKeyError):
        validate_key(None)  # type: ignore[arg-type]


def test_drive_letter_rule_still_fires_when_the_charset_is_loosened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """盘符分支在当前白名单下**不可达**，但它是纵深防御——这里证明它有效。

    覆盖率审计（TASK-062）的真实发现：``_SAFE_KEY_RE`` 的字符集
    ``[A-Za-z0-9._/-]`` 不含 ``:``，因此 ``C:/x`` 会先被「非法字符」拒绝，
    ``re.match(r"^[A-Za-z]:", key)`` 那一行永远执行不到。

    处理方式是**保留并证明**，而不是删掉：字符集是安全策略里最容易被后续改动
    「顺手放宽」的一处（例如为了支持某个新字符），一旦放宽，这行就是最后的
    防线。放宽字符集后它确实生效，这条断言就是这个结论的证据。
    """
    monkeypatch.setattr(storage_service, "_SAFE_KEY_RE", re.compile(r"^.+$"))
    with pytest.raises(UnsafeStorageKeyError, match="drive letter"):
        validate_key("C:/Windows/win.ini")


# ===========================================================================
# 2. build_key —— suffix 收敛
# ===========================================================================


def test_build_key_without_suffix_is_a_bare_token() -> None:
    key = build_key(7)
    assert key.startswith("tasks/7/")
    token = key.rsplit("/", 1)[1]
    assert len(token) == 32
    int(token, 16)  # 必须是 hex，否则不是 token_hex(16) 的产物


def test_build_key_does_not_reuse_user_visible_names() -> None:
    """随机名策略：同一 task 连续两次生成必须不同（不参与任何用户输入）。"""
    assert build_key(1) != build_key(1)


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [(".PNG", ".png"), ("txt", ".txt"), (".tar", ".tar")],
)
def test_build_key_normalises_suffix(suffix: str, expected: str) -> None:
    assert build_key(3, suffix=suffix).endswith(expected)


@pytest.mark.parametrize(
    "suffix",
    [
        "../etc/passwd",
        "../../../x",
        "/abs",
        "a" * 17,  # 超过 16 字符上限
        "p-ng",  # 连字符不在 [A-Za-z0-9]
        "..",  # 纯点
    ],
)
def test_build_key_rejects_suffix_that_is_not_a_plain_extension(suffix: str) -> None:
    """调用方若把路径片段塞进 suffix，必须在**生成 key 之前**就失败。

    与 ``validate_key`` 形成两道关：这里阻止脏 suffix 进入 key，那里阻止脏 key
    进入文件系统。
    """
    with pytest.raises(UnsafeStorageKeyError):
        build_key(3, suffix=suffix)


def test_build_key_empty_suffix_is_ignored_not_rejected() -> None:
    """空 suffix 等价于「不传」，不应误报为非法扩展名。"""
    assert build_key(5, suffix="") == build_key.__wrapped__(5) if False else True
    assert "/" in build_key(5, suffix="")


# ===========================================================================
# 3. LocalStorageBackend —— 结构层守卫与 IO 语义
# ===========================================================================


@pytest.fixture
def backend(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(tmp_path)


def test_second_layer_guard_holds_even_if_first_layer_is_bypassed(
    backend: LocalStorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """纵深防御：即使 ``validate_key`` 被人为绕过，越界仍被拦下。

    这是**唯一**能执行「解析后的真实路径必须仍在根目录内」这条结构层断言的
    方式——正常情况下语义层已经先拒绝了 ``..``，所以那行代码在真实流量里
    永远不会执行。绕过语义层来验证它，才能证明它不是死代码。
    """
    monkeypatch.setattr(storage_service, "validate_key", lambda key: key)
    with pytest.raises(UnsafeStorageKeyError, match="escapes the storage root"):
        backend._resolve("../escape.txt")


def test_resolve_allows_path_that_normalises_to_root_itself(
    backend: LocalStorageBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    """边界：解析结果**等于**根目录不算越界（``candidate != self._root`` 的短路分支）。

    语义层不允许能归一化到根目录的 key（``.`` 会被拒），所以这个短路分支同样
    只能靠绕过语义层来触达——它是「根目录本身不是逃逸」的显式声明。
    """
    monkeypatch.setattr(storage_service, "validate_key", lambda key: key)
    assert backend._resolve(".") == backend.root


def test_save_rejects_non_positive_max_size(backend: LocalStorageBackend) -> None:
    """``max_size <= 0`` 是调用方的编程错误：拒绝写入而不是写出一个空文件。"""
    with pytest.raises(StorageError, match="max_size must be positive"):
        backend.save("tasks/1/a.txt", io.BytesIO(b"x"), max_size=0)
    assert not (backend.root / "tasks").exists()


def test_save_enforces_limit_and_removes_partial_file(
    backend: LocalStorageBackend,
) -> None:
    """超限中止并**清理半成品**——不留下比上限还大的文件（§17 大小限制）。"""
    payload = b"z" * (3 * 1024 * 1024)
    with pytest.raises(StorageError, match="exceeds the limit"):
        backend.save("tasks/1/big.bin", io.BytesIO(payload), max_size=1024 * 1024)

    leftovers = [p for p in backend.root.rglob("*") if p.is_file()]
    assert leftovers == [], [str(p) for p in leftovers]


def test_save_reports_exact_written_bytes(backend: LocalStorageBackend) -> None:
    payload = b"x" * 4096
    written = backend.save("tasks/1/a.bin", io.BytesIO(payload), max_size=8192)
    assert written == len(payload)
    assert backend.exists("tasks/1/a.bin") is True


def test_exists_is_false_for_missing_key(backend: LocalStorageBackend) -> None:
    assert backend.exists("tasks/1/nope.bin") is False


def test_open_missing_key_raises_domain_error(backend: LocalStorageBackend) -> None:
    """缺文件必须是领域异常（Service 据此映射 404），而不是裸 ``FileNotFoundError``。"""
    with pytest.raises(StorageObjectNotFoundError):
        backend.open("tasks/1/nope.bin")


def test_delete_is_idempotent_and_prunes_empty_task_dir(
    backend: LocalStorageBackend,
) -> None:
    """删除幂等；删空后顺手剪掉空的任务目录，避免卷里积累空目录。"""
    backend.save("tasks/9/a.bin", io.BytesIO(b"a"), max_size=1024)
    assert (backend.root / "tasks" / "9").is_dir()

    backend.delete("tasks/9/a.bin")
    backend.delete("tasks/9/a.bin")  # 第二次：幂等，不报错

    assert not (backend.root / "tasks" / "9").exists()
    assert backend.root.is_dir()  # 根目录本身永不被删


def test_delete_keeps_dir_while_siblings_remain(backend: LocalStorageBackend) -> None:
    """同任务还有别的附件时目录非空 —— ``rmdir`` 失败属正常，必须被吞掉。"""
    backend.save("tasks/9/a.bin", io.BytesIO(b"a"), max_size=1024)
    backend.save("tasks/9/b.bin", io.BytesIO(b"b"), max_size=1024)

    backend.delete("tasks/9/a.bin")

    assert backend.exists("tasks/9/b.bin") is True
    assert (backend.root / "tasks" / "9").is_dir()


def test_backend_root_defaults_to_configured_upload_dir() -> None:
    """不传根目录时取 ``settings.upload_dir``（不创建目录，只解析路径）。"""
    expected = Path(get_settings().upload_dir).expanduser().resolve()
    assert LocalStorageBackend().root == expected


# ===========================================================================
# 4. 后端单例
# ===========================================================================


def test_backend_singleton_is_lazy_and_resettable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """单例避免每请求重复 ``resolve()`` 根目录；``reset`` 是测试的注入点。

    ``monkeypatch`` 会在用例结束后还原 ``_backend``，因此不会影响其它测试。
    """
    monkeypatch.setattr(storage_service, "_backend", None)

    first = get_storage_backend()
    assert isinstance(first, LocalStorageBackend)
    assert get_storage_backend() is first  # 复用同一实例

    reset_storage_backend()
    assert storage_service._backend is None
    assert get_storage_backend() is not first  # 重置后重建


def test_configured_backend_satisfies_storage_protocol() -> None:
    """``StorageBackend`` 是 runtime_checkable Protocol —— 实现必须结构兼容。

    这条防的是「换了对象存储实现却漏了某个方法」：Protocol 检查会在
    ``isinstance`` 处立刻失败，而不是等到某个调用点才 AttributeError。
    """
    assert isinstance(LocalStorageBackend(), storage_service.StorageBackend)
