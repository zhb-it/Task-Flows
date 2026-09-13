"""Auth schemas — login request / token response (TASK-016).

`LoginRequest` carries the account identifier (`users.username`) plus the
plain-text password; the password only ever travels from the client to
`verify_password` and is never persisted or logged.

`TokenResponse` currently exposes only the Access Token: the Refresh Token /
JTI pair belongs to TASK-018 (项目文档 §19 双 Token).
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Credentials for `POST /api/v1/auth/login`."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Issued token pair returned by login."""

    access_token: str
    token_type: str = "bearer"
