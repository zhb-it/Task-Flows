# Architecture Decisions

## Decision 001：分层架构
- Problem：避免 HTTP、业务逻辑和数据库操作耦合。
- Decision：Router -> Service -> CRUD -> Model。
- Reason：职责清晰，便于测试与解释。
- Trade-off：文件数量增加，但可维护性更好。

## Decision 002：PostgreSQL
- Decision：使用 PostgreSQL 16。
- Reason：项目需要关系建模、约束、事务、JSONB、GIN、全文搜索等能力。
- Trade-off：本地部署复杂度高于 SQLite。

## Decision 003：Redis
- Decision：Redis 主要用于限流、JWT 黑名单和 Celery Broker/Backend。
- Reason：这些场景需要高性能、TTL/原子操作或消息中间件能力。
- Trade-off：增加一个基础设施依赖。

## Decision 004：Celery
- Decision：耗时且不应阻塞 HTTP 的任务异步执行。
- Reason：通知、日志归档、附件清理不应阻塞主请求。
- Trade-off：需要 Worker、任务重试与幂等设计。

## Decision 005：Task 状态机
- Decision：状态变更必须经过专用 transition API。
- Reason：防止普通 PATCH 绕过业务状态规则。
- Trade-off：API 数量增加，但业务约束更清晰。

## Decision 006：文件存储抽象层
- Problem：§17 要求附件用本地存储，同时预留对象存储迁移；若 Service 直接拼接绝对路径，日后迁移要改动业务流程，且路径穿越防护会散落在多处。
- Decision：定义 `StorageBackend` 协议（`save` / `open` / `delete` / `exists`，全部以相对 key 为参数），本地实现 `LocalStorageBackend` 基于 `UPLOAD_DIR`；`attachments.storage_path` **只存相对 key**，不存绝对路径。
- Reason：把「存什么字节」与「怎么存」解耦；「相对 key → 绝对路径」的转换集中在存储层一处，路径穿越防护只需在那里做对一次；DB 不绑定部署机器的文件系统布局。
- Trade-off：多一层间接（`get_storage_backend()` 单例注入点），换来实现可替换与安全集中。

## Decision 007：上传接口的安全默认值
- Problem：上传是典型高危入口（文件上传漏洞、路径穿越、存储型 XSS、响应头注入、内存耗尽）。
- Decision：
  1. **默认拒绝**的扩展名白名单（不采信客户端 Content-Type，以扩展名判定规范 MIME）；
  2. **随机磁盘名 + 文件名与路径解耦**（`tasks/{task_id}/{token_hex(16)}{ext}`，key 中不含任何用户输入）；
  3. **边写边累计**的大小硬限（不信任 Content-Length，超限即中止并清理半成品）；
  4. 下载响应固定 `X-Content-Type-Options: nosniff`，`Content-Disposition` 用 RFC 5987 百分号编码（结构上杜绝响应头注入）；
  5. 先落盘再落库、落库失败回滚文件；删除时先删文件再删记录。
- Reason：每一条都对应 §9 安全清单中的具体风险项，且都选择「默认安全」而非「可配置」。
- Trade-off：白名单需业务方显式扩充；大文件仍是同步本地 IO 写入（已在 `_UploadReader` 中说明为何与 10MB 上限相容）。

## Decision 008：附件的权限映射
- Problem：§6 权限清单只有 `attachment:upload` / `attachment:download`，没有 `attachment:read` / `attachment:delete`，但需要列表读与删除能力。
- Decision：列表读取**复用 `task:read`**（附件属于任务，读附件即读任务，与评论列表同处理）；删除**复用 `attachment:upload`** 作为功能级门槛，再由资源级判定收敛为「上传者本人或任务所属团队 OWNER/ADMIN」。
- Reason：不擅自新增 §6 之外的权限项（项目规则 §3 不允许猜测）；复用既有权限能让 member 完成正常协作（上传自己的附件、删自己的附件），同时把「删他人附件」限制在管理者。
- Trade-off：删除功能的语义挂在 upload 权限上略不直观，已在端点 docstring 中显式说明。

## Decision 009：非法 storage_path 的两种处理（下载 404 / 删除放行）
- Problem：`attachments.storage_path` 正常由 `build_key` 生成、必然合法；但它可能被绕过 API 改写（DB 被入侵、迁移脚本写错、历史脏数据）。此时存储层抛 `UnsafeStorageKeyError`。若放任未捕获，会变成 500 + 堆栈，把存储根的校验规则泄露给调用者。
- Decision：
  - **下载**：非法 key 与「文件不存在」语义等价 → 统一 404 `Attachment not found`（同文案防枚举），响应体不含任何内部细节；
  - **删除**：捕获该异常、跳过物理删除、继续删记录并正常写审计日志。
- Reason：两个路径的目标不同。下载的目标是「拿到文件」，拿不到就是拿不到，不需要区分原因。删除的目标是**让这条记录消失**——如果也抛错，一条 key 非法的记录将永远删不掉，形成永久脏数据。而那个「文件」本就不在存储根内，我们也不该去碰它。
- Trade-off：删除时不再保证「磁盘上少一个文件」，但这只在脏数据场景发生，且是刻意选择。

## Decision 010：文件名清洗阶段剥离百分号编码
- Problem：`a.txt%00.png` 会按最后一段 `.png` 通过白名单，但 `%00` 一旦在下游任何一处被 URL 解码就变成 NUL 并截断字符串，使「校验时的扩展名」与「实际使用的扩展名」不一致——经典的扩展名绕过（§48 文件上传漏洞）。
- Decision：`sanitize_filename` 在去控制字符**之前**主动剥离所有 `%XX` 序列（`_PERCENT_ESCAPE_RE`），使校验对象与展示对象始终一致。
- Reason：与其假设「下游不会解码」，不如让名字本身不含可解码的转义——把不确定性从整条链路收敛到一个函数里。顺序上必须先于控制字符过滤，否则 `%00` 解码出的 NUL 会绕过该过滤。
- Trade-off：文件名中字面含 `%20` 等序列的用户会被改动展示名（不影响磁盘文件，磁盘用随机 key）。这是可接受的，真实浏览器不会发送这类名字。

## Decision 011：扩展名只取最后一段（白名单契约）
- Problem：`shell.php.txt`、`a.png.exe`、`release.tar.gz` 这类多段扩展名该检查哪一段？「检查所有扩展名」看似更严，实则会误拒 `release.tar.gz` 等正常文件，且与用户对「文件类型」的直觉不符。
- Decision：只取**最后一段**作为类型判定依据；同时磁盘文件名由服务端用白名单解析后的扩展名生成，不含用户提供的中间片段。
- Reason：安全性的来源不是「名字里有几个危险扩展名」，而是「磁盘 key 完全由服务端生成、只带白名单扩展名」+「用户输入不参与路径构造」。因此只判最后一段既安全又符合直觉。把这条固化为契约测试，防止后续以「加强校验」为名改成检查全部扩展名而引入误拒。
- Trade-off：`shell.php.txt` 会被存为 txt 类型；若该文件内容真是 PHP，需由调用方按内容判断（本项目不做内容嗅探，属后续可选项）。
