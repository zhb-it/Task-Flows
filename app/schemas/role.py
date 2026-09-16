"""Role schemas (TASK-082/083).

角色在 API 契约中以 **name** 为标识（种子迁移保证 `admin` / `member` 存在且
name 唯一）；id 仅在数据库内部使用，不出现在请求/响应契约里。
"""

from pydantic import BaseModel, ConfigDict


class RoleRead(BaseModel):
    id: int
    name: str
    description: str | None

    model_config = ConfigDict(from_attributes=True)


class RoleWithPermissionsRead(RoleRead):
    """GET `/permissions`：角色 + 其持有的权限名列表（权限矩阵视图）。"""

    permissions: list[str] = []
