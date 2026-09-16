"""backfill member role for roleless users

TASK-081 数据回填：在「注册默认绑定 member 角色」（应用侧，同一提交内
`register_user` → `assign_role_to_user`）落地之前注册的用户**没有任何角色**，
零角色 = 零权限，登录后所有功能级权限守卫一律 403（「普通成员登录即权限
不足」的根因）。本迁移把存量无角色用户一次性补绑 `member`。

范围判定：
- 只补 `user_roles` 里**一行都没有**的用户（真·无角色）；已有任意角色的
  用户不动——不猜测管理员当初为什么只授了 admin 而不授 member。
- `member` 角色行由种子迁移 0de65c197efc 保证存在；若被手工删除，
  JOIN 不中则 INSERT 0 行（不报错、不造角色——角色是种子数据的职责）。

幂等性：`ON CONFLICT DO NOTHING` 兜底重放；NOT EXISTS 让重复升级不再增行。

downgrade：刻意 no-op。数据迁移无法区分「本迁移回填的 member」与「应用侧
注册时就绑上的 member」，反向删除会误伤后者（CI 的 upgrade→downgrade→
upgrade 链里 downgrade 后紧跟 upgrade，同样靠本迁移恢复，删除无意义）。
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3a7c1f9b2d4'
down_revision: Union[str, None] = '6765bdcfa73e'
branch_labels: Union[str, Sequence[str]] = None
depends_on: Union[str, Sequence[str]] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO user_roles (user_id, role_id)
        SELECT u.id, r.id
        FROM users u
        JOIN roles r ON r.name = 'member'
        WHERE NOT EXISTS (
            SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id
        )
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # no-op：理由见模块 docstring「downgrade」一节。
    pass
