"""Password hashing utilities.

项目文档 §20 规定：密码验证必须位于 `core/security.py`；禁止明文保存密码。
采用 pwdlib 的推荐方案 Argon2id（`PasswordHash.recommended()`）。

明文密码只在本模块内部出现，不写入数据库、不写日志。
"""

from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

# 进程级单例：Argon2id，参数取 pwdlib 推荐值。
_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """把明文密码哈希成可存储的编码串（Argon2id）。

    返回的自描述字符串已包含算法、参数与盐，可直接存入
    `users.password_hash`（`String(255)` 足够容纳）。
    """
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """校验明文密码是否与已存储的哈希匹配。

    若存储的哈希格式非法/无法识别（例如脏数据或非本模块写入的值），
    返回 ``False`` 而不是抛异常，避免登录流程因单条坏数据变成 500。
    """
    try:
        return _password_hash.verify(password, password_hash)
    except UnknownHashError:
        return False
