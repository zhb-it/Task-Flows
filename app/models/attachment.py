"""Attachment ORM model（TASK-042 附件）.

源开发文档 §17 定义 attachments（任务下的文件附件）：

    attachments:
        id
        task_id
        uploader_id
        filename
        storage_path
        content_type
        size
        created_at

§17 上传要求：文件大小限制 / MIME 校验 / 文件名安全处理 / 不允许路径穿越 /
下载必须检查任务访问权限。§51 提供 ``UPLOAD_DIR``（默认 ``storage``）与
``MAX_UPLOAD_SIZE``（默认 10485760，即 10MB）。

TASK-042 已确认决策：

- **task_id FK→tasks ON DELETE CASCADE**：附件必须属于任务（§17），删任务
  级联清其附件元数据（物理文件由清理任务处理，见 §17 / TASK-050）。
- **uploader_id FK→users ON DELETE CASCADE**：附件是用户产出内容，删用户
  级联清其附件元数据（与 ``comments.user_id`` / ``tasks.creator_id`` 同
  惯例）；审计追溯由 OperationLog（TASK-039）承担。
- **storage_path 仅存相对 key**（如 ``tasks/12/ab12cd34.bin``），不是绝对
  路径：物理位置由 ``UPLOAD_DIR`` 决定，DB 不绑定部署机器的文件系统布局，
  便于日后迁移对象存储（§17 预留）。绝对路径拼接与路径穿越防护由
  StorageBackend（``app/services/storage.py``）统一负责。
- **filename 存清洗后的安全名**（去目录分隔符、去控制字符、去首尾点空白、
  限定长度），同时保证 ``storage_path`` 与 ``filename`` 解耦：磁盘上用
  随机名，避免用户可控文件名参与路径构造。
- **content_type**：上传时按扩展名映射白名单校验（§17 MIME 校验），落库为
  校验通过后的规范值；``size`` 为实际写入字节数（流式落盘累计，不信
  Content-Length）。
- **索引 (task_id, created_at)**：附件列表按任务维度 + 时间序查询的主访问
  路径（§17 未显式定义，按查询模式推断并登记）。
- **无 CHECK 约束**：规格未定义枚举值集，size/content_type 的合法性由
  Service 层保证（项目规则 §6：Service 保证业务规则）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func, Index, String, text

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        Index("ix_attachments_task_id_created_at", "task_id", "created_at"),
        Index("ix_attachments_storage_path", "storage_path", unique=True),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    task_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploader_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: 清洗后的安全文件名（仅用于展示与下载时的 filename*，不参与路径构造）。
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 相对存储 key（如 ``tasks/12/ab12cd34.bin``），唯一，不含绝对路径。
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    #: 校验通过后的规范 MIME 类型。
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    #: 实际写入字节数。
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    #: 所属租户（§61.3 多租户，TASK-094）。ON DELETE RESTRICT：租户的删除
    #: 是状态机事务（DECISIONS 065），物理删除租户一律拒绝而非级联清光。
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        # 写入桥接（TASK-094，TASK-095 落认证租户后退化为兜底）：ORM 声明
        # 与 DB 列 DEFAULT 同源——INSERT 未赋值时省略该列、由 DB 归属默认
        # 租户；显式赋值优先（如归档拷贝）。
        server_default=text("current_default_tenant_id()"),
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<Attachment id={self.id} task_id={self.task_id} "
            f"filename={self.filename!r} size={self.size}>"
        )
