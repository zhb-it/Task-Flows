"""Password hashing and JWT utilities.

项目文档 §20 规定：密码验证必须位于 `core/security.py`；禁止明文保存密码。
采用 pwdlib 的推荐方案 Argon2id（`PasswordHash.recommended()`）。

明文密码只在本模块内部出现，不写入数据库、不写日志。
Access Token 的签发/校验同样收敛在本模块（TASK-016），密钥取自配置（`.env`，
不入库、不入日志）。
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

# 进程级单例：Argon2id，参数取 pwdlib 推荐值。
_password_hash = PasswordHash.recommended()

# 签名算法（对称密钥 HMAC-SHA256），Access / Refresh 共用。
_JWT_ALGORITHM = "HS256"

# Token 类别标记：两种 Token 互不通用，防止 Refresh Token 被当作 Access Token 使用。
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


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
    调用方（`app/core/deps.py` 的认证依赖）无需关心 PyJWT 的异常层次。
    """
    return _decode_token(token, ACCESS_TOKEN_TYPE)


def create_refresh_token(subject: str | int) -> tuple[str, str, datetime]:
    """为指定用户签发一个长生命周期的 Refresh Token（JWT）。

    返回 ``(token, jti, expires_at)``：Service 需要用 ``jti`` / ``expires_at``
    在 `refresh_tokens` 表登记，而 Token 本体不落库（开发文档 §55.1
    「保存 Refresh Token JTI」）。

    Claims：
    - ``sub``：用户 id（JWT 规范要求字符串）
    - ``type``：恒为 ``refresh``
    - ``jti``：Token 唯一标识（UUID4），撤销与轮换都按它定位
    - ``iat`` / ``exp``：签发时间与过期时间，时长取自
      ``REFRESH_TOKEN_EXPIRE_DAYS``（默认 7 天）
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.refresh_token_expire_days)
    jti = str(uuid.uuid4())
    payload = {
        "sub": str(subject),
        "type": REFRESH_TOKEN_TYPE,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=_JWT_ALGORITHM)
    return token, jti, expires_at


def decode_refresh_token(token: str) -> dict:
    """校验并解析 Refresh Token，返回其 claims。

    与 `decode_access_token` 对称：签名/过期/类别任一不合法即 ``UnauthorizedError``。
    注意这里**只**保证 Token 本身可信，jti 是否已撤销、账号是否仍可用由
    Service 层查库判断（开发文档 §19「检查数据库 JTI」）。
    """
    return _decode_token(token, REFRESH_TOKEN_TYPE)


def _decode_token(token: str, expected_type: str) -> dict:
    """两种 Token 共用的解码路径：验签、验过期、验类别。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[_JWT_ALGORITHM]
        )
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    return payload
