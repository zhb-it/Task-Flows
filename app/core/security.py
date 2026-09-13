"""Password hashing and JWT utilities.

项目文档 §20 规定：密码验证必须位于 `core/security.py`；禁止明文保存密码。
采用 pwdlib 的推荐方案 Argon2id（`PasswordHash.recommended()`）。

明文密码只在本模块内部出现，不写入数据库、不写日志。
Access Token 的签发/校验同样收敛在本模块（TASK-016），密钥取自配置（`.env`，
不入库、不入日志）。
"""

from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

# 进程级单例：Argon2id，参数取 pwdlib 推荐值。
_password_hash = PasswordHash.recommended()

# Access Token 签名算法（对称密钥 HMAC-SHA256）。
_JWT_ALGORITHM = "HS256"

# Token 类别标记：防止 TASK-018 的 Refresh Token 被当作 Access Token 使用。
ACCESS_TOKEN_TYPE = "access"


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


def create_access_token(subject: str | int) -> str:
    """为指定用户签发一个短生命周期的 Access Token（JWT）。

    Claims：
    - ``sub``：用户 id（JWT 规范要求字符串）
    - ``type``：恒为 ``access``，用于区分（TASK-018 的）Refresh Token
    - ``iat`` / ``exp``：签发时间与过期时间，过期时长取自
      ``ACCESS_TOKEN_EXPIRE_MINUTES``（默认 30 分钟）
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(subject),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """校验并解析 Access Token，返回其 claims。

    签名错误、已过期、类别不符都会被统一转换为 ``UnauthorizedError``（401），
    调用方（后续 TASK-017 的认证依赖）无需关心 PyJWT 的异常层次。
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[_JWT_ALGORITHM]
        )
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise UnauthorizedError("Invalid token type")
    return payload
