"""Comment Service（TASK-041）.

事务边界在本层（项目规则 §4）。§16 四条规则落位：

1. **用户必须有任务访问权限才能评论**——归属链校验（任务 → 项目 → 团队 →
   ``team_members``，复用 task 服务的可见性原语），不在链上 → 404 防枚举；
2. **评论必须属于任务**——``task_id`` 由路径给出，创建时校验任务在归属链上；
3. **删除评论需要权限**——TASK-041 决策（用户确认）：功能级 ``comment:delete``
   （Router 依赖）+ 资源级**评论作者本人或任务所属团队 OWNER/ADMIN**；
   已在链上但两者都不是 → 403；不在链上 → 404（IDOR 契约）；
4. **删除行为写入操作日志**——复用 OperationLog（TASK-039）：同一事务内写
   ``action=comment:delete`` / ``payload={task_id, comment_id}``。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ResourceNotFoundError
from app.crud.comment import (
    create_comment as create_comment_crud,
    delete_comment as delete_comment_crud,
    get_comment,
    list_comments_by_task,
)
from app.crud.project import get_project, is_project_visible
from app.crud.task import get_task
from app.models.task import Task
from app.models.team_member import TeamRole
from app.models.user import User
from app.schemas.comment import CommentRead
from app.services.operation_log import write_operation_log
from app.services.team import team_membership

COMMENT_NOT_FOUND = "Comment not found"
TASK_NOT_FOUND = "Task not found"
NOT_MANAGER = "Only team owner or admin or the comment author can delete comments"


async def create_comment(
    db: AsyncSession, user: User, task_id: int, content: str
) -> CommentRead:
    """在任务下发表评论（规则 1/2）：须在任务归属链上。"""
    task = await _get_task_on_chain(db, user, task_id)
    comment = await create_comment_crud(
        db, task_id=task.id, user_id=user.id, content=content
    )
    await db.commit()
    return CommentRead(
        id=comment.id,
        task_id=comment.task_id,
        user_id=comment.user_id,
        username=user.username,
        content=comment.content,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


async def list_comments(
    db: AsyncSession, user: User, task_id: int, *, skip: int = 0, limit: int = 100
) -> list[CommentRead]:
    """任务下评论列表（规则 1）：须在任务归属链上，否则 404。"""
    await _get_task_on_chain(db, user, task_id)
    rows = await list_comments_by_task(db, task_id, skip=skip, limit=limit)
    return [
        CommentRead(
            id=c.id,
            task_id=c.task_id,
            user_id=c.user_id,
            username=username,
            content=c.content,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c, username in rows
    ]


async def delete_comment(db: AsyncSession, user: User, comment_id: int) -> None:
    """删除评论（规则 3/4）：作者本人或任务所属团队 OWNER/ADMIN。

    - 评论不存在 / 评论所属任务不在归属链 → 404 Comment not found
      （同文案防枚举）；
    - 已在链上但既非作者、团队角色也不足 → 403 明示（调用者本就可见
      该评论，无泄露顾虑）；
    - 成功 → 删行并在同一事务内写 ``action=comment:delete`` 审计日志。
    """
    comment = await get_comment(db, comment_id)
    if comment is None:
        raise ResourceNotFoundError(COMMENT_NOT_FOUND)

    task = await get_task(db, comment.task_id)
    # 归属链校验（任务必然存在——FK CASCADE 保证评论不悬挂）
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(COMMENT_NOT_FOUND)

    if comment.user_id != user.id:
        project = await get_project(db, task.project_id)
        assert project is not None  # 归属链已通过，项目必然存在
        role = await team_membership(db, project.team_id, user.id)
        if role not in (TeamRole.OWNER, TeamRole.ADMIN):
            raise ForbiddenError(NOT_MANAGER)

    task_id = comment.task_id
    await delete_comment_crud(db, comment)
    await write_operation_log(
        db,
        user_id=user.id,
        resource_type="comment",
        resource_id=comment_id,
        action="comment:delete",
        payload={"task_id": task_id, "comment_id": comment_id},
    )
    await db.commit()


async def _get_task_on_chain(
    db: AsyncSession, user: User, task_id: int
) -> Task:
    """任务不存在或调用者不在归属链上 → 404（IDOR 防枚举）。"""
    task = await get_task(db, task_id)
    if task is None or not await _is_task_visible(db, task, user.id):
        raise ResourceNotFoundError(TASK_NOT_FOUND)
    return task


async def _is_task_visible(db: AsyncSession, task: Task, user_id: int) -> bool:
    """任务可见性 = 调用者在任务所属项目的团队成员链上。"""
    return await is_project_visible(
        db, project_id=task.project_id, user_id=user_id
    )
