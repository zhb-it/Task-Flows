"""文件存储抽象层（TASK-042，源文档 §17）.

§17 要求附件使用本地存储并预留向对象存储迁移的空间，因此这里把「存什么
字节」与「怎么存」拆开：

- :class:`StorageBackend` —— 协议（Protocol），只暴露 ``save`` / ``open`` /
  ``delete`` / ``exists`` 四个语义化操作，全部以**相对 key** 为参数。
- :class:`LocalStorageBackend` —— 基于本地文件系统的实现，根目录取
  ``settings.upload_dir``。

调用方（Attachment Service）永远不接触绝对路径，也不知道底层是本地磁盘还是
对象存储；日后换成 S3/MinIO 只需提供另一个 StorageBackend 实现。

安全要点（§9 文件上传漏洞 / 路径穿越）：

本模块是**唯一**做「相对 key → 绝对路径」转换的地方，因此路径穿越防护集中
在这里实现，而不是散落在 Service。若把拼接下推到调用方，任何一处忘记校验
都会形成穿越漏洞。
"""

from __future__ import annotations

import os
import re
import secrets
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from app.core.config import get_settings

#: 相对 key 允许的字符集：受限字母数字 + ``/`` 分隔 + ``.``/``_``/``-``。
#: 上传侧生成的 key 一定落在此集合内，此处再做一次白名单校验以防调用方传入
#: 手工拼装的 key（如 ``../`` 或绝对路径）。
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9._/-]+$")

#: 单次读取的块大小（1MB）。流式读写在 Service 侧也按这个粒度累计大小。
CHUNK_SIZE = 1024 * 1024


class StorageError(Exception):
    """存储层错误基类。"""


class UnsafeStorageKeyError(StorageError):
    """key 非法（含穿越片段、绝对路径或非法字符）——拒绝访问。"""


class StorageObjectNotFoundError(StorageError):
    """key 在存储中不存在。"""


@runtime_checkable
class StorageBackend(Protocol):
    """对象存储的最小接口（§17 预留对象存储迁移）。"""

    def save(self, key: str, data: BinaryIO, *, max_size: int) -> int:
        """把 ``data`` 写入 ``key``，返回实际写入的字节数。

        ``max_size`` 是硬上限：写入过程中一旦超限必须中止并清理半成品。
        """
        ...

    def open(self, key: str) -> BinaryIO:
        """以二进制只读方式打开 ``key``。不存在时抛
        :class:`StorageObjectNotFoundError`。"""
        ...

    def delete(self, key: str) -> None:
        """删除 ``key``；不存在时视为成功（幂等）。"""
        ...

    def exists(self, key: str) -> bool:
        """``key`` 是否存在。"""
        ...


def validate_key(key: str) -> str:
    """校验并归一化相对 key，返回可直接用于本地拼接的字符串。

    规则：

    - 非空字符串，且不含 ``\\``（Windows 分隔符统一由 ``/`` 表达）；
    - 仅允许 :data:`_SAFE_KEY_RE` 字符集；
    - 不能是绝对路径（不以 ``/`` 开头，不含盘符）；
    - 按 ``/`` 拆分后不含空段、``.``、``..`` 段。

    违规一律抛 :class:`UnsafeStorageKeyError`，不做任何「清洗后放行」——
    容忍脏 key 会把风险留给未来。
    """
    if not isinstance(key, str) or not key:
        raise UnsafeStorageKeyError("storage key must be a non-empty string")
    if "\\" in key:
        raise UnsafeStorageKeyError("storage key must not contain backslashes")
    if not _SAFE_KEY_RE.match(key):
        raise UnsafeStorageKeyError("storage key contains illegal characters")
    if key.startswith("/"):
        raise UnsafeStorageKeyError("storage key must be relative")
    parts = key.split("/")
    for part in parts:
        if part in ("", ".", ".."):
            raise UnsafeStorageKeyError(
                "storage key must not contain empty or traversal segments"
            )
    # 防御盘符式前缀（如 C:foo），即便字符集检查已基本覆盖。
    if re.match(r"^[A-Za-z]:", key):
        raise UnsafeStorageKeyError("storage key must not contain a drive letter")
    return key


def build_key(task_id: int, *, suffix: str = "") -> str:
    """按 ``tasks/{task_id}/{random}{suffix}`` 生成相对 key。

    **随机名策略**：磁盘上的文件名与用户提供的 ``filename`` 完全解耦，用户
    可控字符串不参与路径构造，从根上消灭「用文件名做穿越」这一类问题；
    原始文件名只作为展示字段存在数据库里。

    ``suffix`` 由调用方从已校验的白名单扩展名给出（含点号，如 ``.png``）。
    """
    token = secrets.token_hex(16)
    safe_suffix = ""
    if suffix:
        # 再次收敛：扩展名只能是字母数字，防止调用方把路径片段塞进来。
        candidate = suffix if suffix.startswith(".") else f".{suffix}"
        if not re.match(r"^\.[A-Za-z0-9]{1,16}$", candidate):
            raise UnsafeStorageKeyError("illegal suffix passed to build_key")
        safe_suffix = candidate.lower()
    return f"tasks/{task_id}/{token}{safe_suffix}"


class LocalStorageBackend:
    """本地文件系统实现（§17 默认方案）。

    实例化时只记录根目录，不主动创建目录；``save`` 时才按需 ``mkdir``。
    根目录可注入（测试用 ``tmp_path`` 隔离，不污染真实 ``storage/``）。
    """

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        if root is None:
            root = get_settings().upload_dir
        self._root = Path(root).expanduser().resolve()

    @property
    def root(self) -> Path:
        """存储根目录（绝对路径，仅本类内部与测试使用）。"""
        return self._root

    def _resolve(self, key: str) -> Path:
        """把相对 key 解析成根目录下的绝对路径，并二次确认未越界。

        :func:`validate_key` 已在语义层挡住穿越，这里再做一次「解析后的真实
        路径必须仍在根目录内」的_结构层_断言——两层都过才算安全（§9）。
        """
        validate_key(key)
        candidate = (self._root / key).resolve()
        if candidate != self._root and self._root not in candidate.parents:
            raise UnsafeStorageKeyError("storage key escapes the storage root")
        return candidate

    def save(self, key: str, data: BinaryIO, *, max_size: int) -> int:
        """流式写入并返回实际字节数；超限则删除半成品并抛错。

        不信任 ``Content-Length``：边写边累计，超过 ``max_size`` 立即中止
        （§17 文件大小限制）。
        """
        if max_size <= 0:
            raise StorageError("max_size must be positive")
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with target.open("wb") as fh:
                while True:
                    chunk = data.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_size:
                        raise StorageError(
                            f"uploaded file exceeds the limit of {max_size} bytes"
                        )
                    fh.write(chunk)
        except Exception:
            # 任何失败（含超限）都不留下半成品文件。
            target.unlink(missing_ok=True)
            raise
        return written

    def open(self, key: str) -> BinaryIO:
        """打开只读句柄；不存在时抛 :class:`StorageObjectNotFoundError`。"""
        target = self._resolve(key)
        try:
            return target.open("rb")
        except FileNotFoundError as exc:
            raise StorageObjectNotFoundError(key) from exc

    def delete(self, key: str) -> None:
        """删除文件（幂等）；顺带清理空的任务目录。"""
        target = self._resolve(key)
        target.unlink(missing_ok=True)
        parent = target.parent
        if parent != self._root:
            try:
                parent.rmdir()
            except OSError:
                # 目录非空（同任务还有其它附件）——正常情况，忽略。
                pass

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()


_backend: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """返回进程内单例存储后端。

    单例避免每个请求重复 ``resolve()`` 根目录；测试若需替换，直接对
    ``app.services.storage._backend`` 赋值注入即可（依赖注入点只有这一处）。
    """
    global _backend
    if _backend is None:
        _backend = LocalStorageBackend()
    return _backend


def reset_storage_backend() -> None:
    """清空单例（测试夹具用）。"""
    global _backend
    _backend = None
