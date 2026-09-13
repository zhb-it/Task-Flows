"""Auth schemas — login / refresh request and token response (TASK-016, TASK-018).

`LoginRequest` carries the account identifier (`users.username`) plus the
plain-text password; the password only ever travels from the client to
`verify_password` and is never persisted or logged.

`TokenResponse` is the pair issued by login **and** by refresh (开发文档 §19
双 Token / §55.1 登录流程). `RefreshRequest` carries the Refresh Token in the
body — the project has no cookie/session mechanism, every credential travels
through an explicit request field.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Credentials for `POST /api/v1/auth/login`."""

    username: str
    password: str


class RefreshRequest(BaseModel):
    """Body of `POST /api/v1/auth/refresh`."""

    refresh_token: str


class TokenResponse(BaseModel):
    """Issued token pair returned by login and refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
