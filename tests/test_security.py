"""TASK-014：密码哈希与安全模块的离线测试（无需数据库）。"""

import pytest

from app.core.security import hash_password, verify_password

PLAIN = "S3cret-Passw0rd!"


def test_hash_returns_str_and_is_not_plaintext() -> None:
    hashed = hash_password(PLAIN)
    assert isinstance(hashed, str)
    assert hashed != PLAIN
    # 明文绝不能出现在哈希结果中。
    assert PLAIN not in hashed


def test_hash_uses_argon2id() -> None:
    # pwdlib 推荐方案即 Argon2id，前缀可据此判断实际算法。
    assert hash_password(PLAIN).startswith("$argon2id$")


def test_hash_fits_password_hash_column() -> None:
    # `users.password_hash` 为 String(255)，哈希必须能装下。
    assert len(hash_password(PLAIN)) <= 255


def test_same_password_hashes_differently() -> None:
    # 每次哈希使用独立随机盐，故两次结果不同。
    assert hash_password(PLAIN) != hash_password(PLAIN)


def test_verify_accepts_correct_password() -> None:
    assert verify_password(PLAIN, hash_password(PLAIN)) is True


def test_verify_rejects_wrong_password() -> None:
    assert verify_password("wrong-password", hash_password(PLAIN)) is False


@pytest.mark.parametrize(
    "malformed",
    ["", "not-a-hash", "$2b$12$invalid", "$argon2id$broken"],
)
def test_verify_returns_false_for_malformed_hash(malformed: str) -> None:
    # 坏哈希返回 False 而非抛异常（避免登录流程 500）。
    assert verify_password(PLAIN, malformed) is False


def test_long_password_supported() -> None:
    # Argon2 无 bcrypt 的 72 字节截断限制。
    long_password = "p" * 200
    assert verify_password(long_password, hash_password(long_password)) is True


def test_case_sensitive_and_unicode() -> None:
    hashed = hash_password("Paßwörd-中文-123")
    assert verify_password("Paßwörd-中文-123", hashed) is True
    assert verify_password("paßwörd-中文-123", hashed) is False
