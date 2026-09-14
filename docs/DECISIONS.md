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

## Decision 012：Redis 客户端共享单例（而非每请求新建 / 注入 app.state）
- Problem：§21 要求 Redis 承担五项用途，若每处 `Redis.from_url(...)` 各自创建，或每个请求新建一个 client，都会重复创建连接池（`redis.asyncio.Redis` 内部持有一个 `ConnectionPool`），是典型的连接/内存泄漏；同时「应用到底怎么连 Redis」会出现多份真相。
- Decision：`app/db/redis.py` 作为**唯一连接入口**：模块级 `_client` 惰性单例 + `get_redis_client()`；FastAPI 侧提供 `get_redis()` 依赖（`Depends(get_redis)`）yield 共享实例。**关键差异**：`get_redis()` **不关闭** yield 出的客户端——这与 `get_db()` 每请求一份、请求结束必须关闭形成刻意对比。
- Reason：数据库 `Session` 是**有状态的每请求工作单元**（事务边界即请求边界），必须关闭；Redis 客户端是**无状态的连接池句柄**，其「连接」由池按需借还，跨请求复用一个实例才是正确用法。关闭它会让其它并发请求/后续请求拿到的实例失效。用依赖注入而非 `app.state`/全局变量，是为了与既有 `get_db` 惯例一致，并让测试可用 `app.dependency_overrides` 覆盖。
- Trade-off：引入进程级可变状态（`_client`），因此配套提供 `close_redis()`（lifespan shutdown 释放）与 `reset_redis()`（测试清引用）。若将来需要多实例（如读写分离），此单例会成为约束点——但在 §21 的五个用途下没有这个需求，遵守「不为用而用」。

## Decision 013：Redis Key 命名约定 `taskflow:<purpose>:<identifier>`
- Problem：§21 的多个用途共用同一 Redis 实例（甚至同一 DB）。若各处独立拼字符串：①前缀不一致会让同一逻辑数据出现两份，TTL 与清理互相打架；②某人改了前缀而漏改另一处 → 线上「限流突然失效」这类极难排查的故障；③无法一眼分辨哪些键是本应用的，运维清理时可能误删他人数据。
- Decision：`app/core/redis_keys.py` 是**唯一的 Key 构造点**（与 `app/services/storage.py` 的 `build_key` 同一思路——把「命名」收敛到一个函数）。格式 `taskflow:<purpose>:<identifier>`：`taskflow` 全局命名空间前缀（使 `SCAN taskflow:*` 成为安全运维操作）、`<purpose>` 与 §21 用途清单一一对应（`ratelimit`/`jwt`/`celery`）、`<identifier>` 为调用方提供的业务标识。`build_key` 拒绝空 purpose 与含 `:` 的 purpose，非字符串 part 自动 `str()`。具体构造器：`rate_limit_key(scope, identifier)`、`jwt_blacklist_key(jti)`。
- Reason：①命名集中后「Key 与 TTL 一起评审」才可能（两者是一体两面的契约——`jwt:blacklist:*` 的 TTL 必须不小于 Token 剩余寿命，否则 Token 会在过期前被放出黑名单；限流窗口的 TTL 必须覆盖整个窗口）；②`ratelimit:<scope>:<value>` 的多段结构让我们能对某 scope 整体扫描清理，而不必枚举所有可能的值；③purpose 拒绝 `:` 是**显式失败**优于静默拼接——静默拼接会让「用途段」结构失效，且问题会潜伏到线上才发现。
- Trade-off：前缀 `KEY_PREFIX` 变更是破坏性操作（等同迁移所有已存在键），因此测试里用字面量显式钉住而非引用常量，避免形成「常量改了断言跟着改」的循环、使断言失去意义。

## Decision 014：本 TASK 只做连接与 Key，不提前接入黑名单校验链路
- Problem：§21 列出 JWT 黑名单用途，本 TASK 已定义 `jwt_blacklist_key`。是否应顺手把校验接入 `get_current_user`？
- Decision：**不接**。本 TASK 只交付连接层与 Key 约定；ZSET+Lua 限流属 TASK-046，JWT 黑名单校验链路留待真正出现「需要让 Access Token 提前失效」的需求时再做（§19 的登出目前靠数据库撤销 Refresh Token 的 jti 已满足）。
- Reason：①在 `get_current_user` 这个认证热路径上新增一次 Redis 往返，会给**每个受保护请求**都加一次网络调用——没有需求驱动就改热路径，违反 §44「不为用缓存而用缓存」与规则 §7「不为使用 Redis 而使用 Redis」；②先接入再去需求会导致「实现超前于验证」，无法说清它解决了什么真实问题（§3.1 禁止为了简历包装而添加无法解释的技术）。
- Trade-off：`jwt_blacklist_key` 暂时无调用方（仅被测试覆盖）。这是**有意的占位契约**——它把「未来接入时键长什么样」这件事提前钉死，接入时才不会即兴命名。为免「创建没有实际用途的空模块」之嫌，本模块的其余部分（`build_key`/`rate_limit_key`）已被 TASK-046 立即消费。
