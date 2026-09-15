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

## Decision 015：限流阈值采用可覆盖的默认值（规格未定义数值）
- Problem：§22 规定了限流**机制**（ZSET + Lua + 滑动窗口 + 429），但**没有给出任何数值**——窗口多长？窗口内允许多少请求？按项目规则 §3「不允许猜测业务规则」，实现者不能自行编造业务参数。
- Decision：设为 `rate_limit_requests=60`、`rate_limit_window_seconds=60`（即每分钟 60 次），`rate_limit_enabled=True`，三者都在 `Settings` 中，可经 `.env` 覆盖。**已与用户确认**采用此方案。
- Reason：①60/60 是业界最常见的默认档位，对正常使用足够宽松、对滥用在量级上有效；②放进 `Settings` 而非硬编码，使「数值」属于部署配置而非代码逻辑——这正是配置与业务规则的正确分界；③`rate_limit_enabled` 开关让本地压测/调试可以整体旁路，不必改代码。
- Trade-off：默认值仍是一个**假设**（规格没给）。为可追溯，本条 Decision 显式记录「数值来自实现者选择而非规格」，并在 TESTING 中说明阈值可覆盖。若将来确定业务参数，只需改 `.env` 或 Settings 默认，不改算法。

## Decision 016：限流必须连真实 Redis 测试（不 mock）
- Problem：限流的正确性高度依赖 Redis 的真实行为——Lua 能否 EVAL、`TIME` 返回什么、ZSET 的 score 语义、`PEXPIRE` 的作用范围。用假客户端（fake/mock）测可以跑得很快，但这些恰恰是最容易出错的地方。
- Decision：`tests/test_rate_limit.py` 的 Lua 语义层与中间件层**全部连真实 Redis**（宿主 6389）；只有「配置项存在性」这类纯静态断言离线跑。不可达时 `skip` 而非失败。
- Reason：限流被击穿的三个最常见根因——①判断与写入之间存在竞态（必须用真实 Redis 并发验证）；②member 不唯一导致 ZSET 折叠、计数偏低；③TTL 没设或设错导致 ZSET 无界增长——**在假客户端上一个都测不出来**。把它们排除在覆盖之外，等于交付一个「测试全绿但线上会被绕过」的限流。
- Trade-off：测试依赖本机 Redis 与网络（比纯单测脆），且串行跑约 3 秒。换取的是「测试真的在验证交付物」——用**变异测试**证实：把 Lua 中的 `if current >= max_requests` 改为恒假后，10 个用例立即失败（含并发原子性用例），证明断言承重。

## Decision 017：中间件身份判定不查库；Redis 故障时 fail-open
- Problem：按 §22 需要「IP / User」两维度。已认证请求要拿到 user 维度标识，是否应在中间件里查库确认用户存在？另外 Redis 不可用时 HTTP 请求该如何处理？
- Decision：
  1. 中间件**只解 JWT 的 `sub`**（纯计算，无 IO），**不查库**；解不出来（未认证/Token 非法）退化为 IP 维度。
  2. Redis 故障时**放行**（fail-open），只记 warning 日志。
- Reason：①中间件在路由层之前运行，此时 `get_db` 尚未建立（它是端点级依赖）；在此查库等于给每个请求（含未认证请求）都加一次数据库往返，而限流的初衷恰恰是**保护数据库**，自相矛盾。用户是否存在/是否禁用本来就是端点内 `get_current_user` 的职责——限流不需要这个结论，它只需要一个**稳定的区分键**。②限流是保护性措施，不应成为新的单点故障：Redis 一挂就让整个 API 不可用，代价远大于「短时限流失效」。Redis 故障由 `/health` 暴露，是可观测的已知状态。
- Trade-off：①用 `sub` 而不校验用户存在，意味着被删除用户的有效 Token 仍会在 user 维度计数——无害（该请求随后会在认证层被 401）；②fail-open 期间无限流保护。两者都是刻意选择：宁可「保护暂时失效」，不要「服务整体不可用」。

## Decision 018：`Retry-After` 由窗口内最早请求推算；不做 `X-Forwarded-For` 信任
- Problem：429 若不告知等待时间，客户端只能盲目重试，反而加剧限流。另外经反代部署时是否应解析 `X-Forwarded-For` 取真实 IP？
- Decision：
  1. 被拒时返回 `Retry-After`（秒），值 = 「窗口内**最早**成员离开窗口所需时间」向上取整（至少 1）。
  2. IP 维度**只**用 `request.client.host`，**不**解析 `X-Forwarded-For`。
- Reason：①最早成员最先离开窗口，因此它就是「多久后能再发请求」的准确下界——用窗口总长会让客户端无谓多等。②`X-Forwarded-For` 可被客户端任意伪造，用它做限流标识等于让攻击者随手换身份绕过限制。真实 IP 的信任边界属于反代配置（Nginx 覆盖而非追加），是 TASK-060 的部署层决策，不应在应用代码里提前假设。
- Trade-off：①额度刚被占满时 `Retry-After` 可能接近整个窗口长度（因为最早成员才刚进来），这是准确的；②在 Nginx 后，所有请求的 `client.host` 都是 Nginx 的地址，IP 维度会退化为「所有匿名用户共享一个配额」。这一点在 TASK-060 接入反代时**必须**一并解决（届时按部署拓扑决定是否信任反代写入的头），已记入 PROGRESS 作为遗留约束。

## Decision 019：Redis 调用必须有延迟上界；`.env` 用 `127.0.0.1` 而非 `localhost`
- Problem（**TASK-046 期间由测试暴露的真实缺陷**）：接入限流中间件后，全量测试从约 5 分钟劣化到 15 分钟以上并卡死。定位发现单个用例从 <1s 涨到 **27s**。根因有三层，逐层剥开才看清：
  1. `.env` 的 `REDIS_URL=redis://localhost:6379/0` 指向的**不是本项目的 Redis**。compose 把项目 Redis 发布在**宿主 6389**（`6389:6379`），而 6379 上另有一个**需要 AUTH 的 Redis**（裸 socket 能瞬时连上、并发回 `-NOAUTH Authentication required.`）。
  2. 客户端不带密码 → 收到 NOAUTH → `redis.asyncio` 按默认重试策略反复重试，直到默认 socket 超时。而**默认超时很宽松**，实测单次 `PING` 失败要 **5.02s**，叠加重试即 27s。
  3. 限流中间件对**每个 `/api/v1` 请求**都要访问 Redis，于是这个「每次 5s+」的成本被乘到每一个请求上——测试表现为「卡住不动」，实为每个请求在等超时。
  另有一个独立陷阱：Windows 上 `localhost` 会**优先解析到 IPv6 `::1`**（`getaddrinfo` 实测 `::1` 在 `127.0.0.1` 之前），而 Docker 只把端口发布在 IPv4 上——即使把端口改对成 6389，写 `localhost:6389` 仍会连 `::1` 而挂到超时。
- Decision：
  1. `app/db/redis.py` 的客户端**显式设置** `socket_timeout` 与 `socket_connect_timeout`（`REDIS_SOCKET_TIMEOUT_SECONDS = 1.0`）。
  2. 中间件在 socket 超时之外**再加一层 `asyncio.timeout`**（`RATE_LIMIT_CALL_TIMEOUT_SECONDS = 2.0`）作为兜底，双保险封顶单请求额外延迟。
  3. `.env` 的 `DATABASE_URL` 与 `REDIS_URL` 一律改用 **`127.0.0.1`** 并指向正确端口（5433 / 6389），并在文件中注释说明原因。
- Reason：①限流的价值远小于「让每个请求慢 5 秒」的代价——fail-open 若没有延迟上界，比拒绝请求更糟（请求变慢而非快速失败，还会耗尽 worker）。健康的 Redis 在同机/同机房应 <10ms，1s 超时给足余量。②在应用代码里设超时是**代码级保证**，不依赖部署环境是否配对了正确的 URL——即使运维配错地址，最坏情况也是「限流失效 + 每请求多 1s」，而不是服务雪崩。③`127.0.0.1` 消除 IPv6/IPv4 的解析歧义，是 Windows + Docker Desktop 环境下唯一确定的行为。
- Trade-off：①Redis 真被跨机房部署且 RTT > 1s 时会被误判为超时、导致限流失效——这是刻意选择（宁可限流失效也不要请求变慢），且本项目 Redis 与 API 同机部署；②`.env` 是本机配置（gitignored），此修复不影响他人，但 `.env.example` 与文档中的相关说明需要保持一致。
- **可测性收益**：修复后限流单次调用实测 **0.6ms**（50 次共 0.029s），中间件开销可忽略；此前「卡住」的单个用例从 27s 回到正常水平。

## Decision 020：限流失败路径的显式测试（Redis 挂掉时会发生什么）
- Problem：fail-open 是一条「只在故障时走」的分支，正常测试永远不会覆盖。若不显式测试，它可能悄悄退化为 fail-closed（Redis 挂 → 全站 429）或无限等待，而这两种情况在 Redis 真挂掉时才会暴露——那时已经来不及。
- Decision：`tests/test_rate_limit.py::test_redis_failure_fails_open` 用 monkeypatch 让 `check_rate_limit` 抛 `ConnectionError`，断言连续 5 个请求**都未被 429 拦截**（仍到达业务层得到 401）。
- Reason：故障路径的测试价值高于正常路径——正常路径出错会立刻被发现，故障路径出错只会在真正故障时被放大成事故。把它固化为回归测试，任何「顺手改成 fail-closed」或「忘记包 try」的改动都会立刻失败。
- Trade-off：monkeypatch 模拟的是「Redis 抛错」，而非真实的网络超时；真实超时路径由 Decision 019 的 `asyncio.timeout` 与 socket 超时共同保证（已单独验证单请求耗时上界为 1.02s）。

## Decision 021：测试套件默认关闭限流（`tests/conftest.py`），限流测试自行开启
- Problem（**TASK-046 全量回归暴露**）：限流中间件对每个 `/api/v1` 请求生效后，全量回归出现 2 个失败——`test_refresh.py` 的 `test_refresh_token_signed_with_other_secret_returns_401` 与 `test_malformed_subject_returns_401` 断言应为 401，实际得到 **429**（`Rate limit exceeded: 60 requests per 60 seconds`）。根因：所有测试文件的客户端共用同一来源地址（`ASGITransport` 默认 `127.0.0.1`），因此**共享同一个 IP 维度的限流键**；`test_refresh.py` 单文件的请求数就超过 60 次/分钟，触发了真实的限流。
- Decision：新增 **`tests/conftest.py`**，用 autouse fixture 在**全测试套件默认关闭限流**（`rate_limit_enabled=False`）；`tests/test_rate_limit.py` 在自己的用例内用 `monkeypatch.setattr(settings, "rate_limit_enabled", True)` 显式开启，并同时设置很小的额度来快速触发 429。
- Reason：①这不是实现缺陷，而是**测试之间的隐式耦合**——一个测试的结果取决于它之前跑过多少测试，这类非确定性必须消除；②备选方案「给每个文件分配独占 IP」只能解决 IP 维度，无法解决「单个文件内请求数超额度」，且要改动 40 个既有文件；③默认关闭、按需开启的语义最清晰：其他测试关心的是业务行为（认证、权限、状态机），限流不属于它们的测试目标；④monkeypatch 会在用例结束时自动还原，且限流测试显式覆盖该默认值，因此**覆盖率不受影响**。
- Trade-off：默认配置与生产默认（开启）不一致——这是测试夹具的常规做法（如测试库 vs 生产库）。为避免「忘记开启导致限流其实没测」的风险，`test_rate_limit.py` 的每个相关用例都显式设置 `rate_limit_enabled=True`，且新增了 3 项直接针对限流配置与延迟上界的离线断言（Decision 019/020）。

## Decision 022：配额是**身份级**的，在所有 `/api/v1` 端点间共享
- Problem：§22 的链路是 `IP / User → Redis ZSET → …`，只给出身份维度，**没有端点维度**。因此 TASK-046 的实现天然是「一个身份一个 ZSET，所有端点共享一份额度」。这个语义若不写下来，很容易在后续重构中被无意改变（例如有人「顺手」按 `path` 分段取键，于是同一用户可以对每个端点各打满额度，等效额度放大 N 倍）。
- Decision：保持现状（身份级共享），并在 `tests/test_rate_limit_integration.py::test_quota_is_shared_across_all_api_endpoints` 中固化——同一用户在 `/api/v1/users/me` 与 `/api/v1/teams` 之间切换，额度不因换端点而重置。
- Reason：①忠实于 §22——链路里没有端点维度；②**限流的目的是保护后端整体**（数据库、Redis、worker），而不是保护某个端点，按端点切分会让「打满所有端点」的总量仍然失控；③按端点取键会引入「端点数量 × 身份数量」的键空间，对 Redis 内存与 `SCAN` 运维都不友好。
- Trade-off：某些低频但昂贵的操作（如上传大附件）会与高频廉价请求争抢同一份额度。当前不引入「按端点差异化配额」——§22 未要求，属新增功能（规则 §3/§5）。若将来确有需要，应作为**有意识的设计变更**并同步修改本决策与本测试。

## Decision 023：限流只判定、**不落审计**（`operation_logs` 不记录被限流的请求）
- Problem：TASK-046 只断言了被限流请求的状态码是 429，没有回答「它会不会写 `operation_logs`」。两者都合理：写，能追溯攻击；不写，语义干净。若不固化，后续「顺手加审计」会改变 §15/§16 的语义边界。
- Decision：**不写**。由 `tests/test_rate_limit_integration.py::test_throttled_requests_do_not_write_operation_logs` 固化：一次成功的流转产生 1 条 `task:transition` 日志，此后被打到的 429 请求产生 0 条。
- Reason：①`operation_logs` 记录的是**发生过的业务动作**（§15），被限流的请求根本没到业务层，记录它等于伪造事实；②洪水会把审计表灌满并淹没真正的审计线索——这恰好与「限流是为了保护系统」的初衷相反；③与 TASK-044 固化的「创建评论 / 上传附件不写日志」是同一条边界（只记录改变状态的动作）。
- Trade-off：失去了「从审计表复盘一次洪水攻击」的能力。攻击行为应由访问日志 / Redis 键观测承担，而不是业务审计表。

## Decision 024：429 先于认证，且不泄露内部标识
- Problem：限流是中间件、认证是路由依赖，因此 429 必然先于 401 产生。这个顺序既是必要的（否则不带 Token 的洪水可以无限打认证端点），也带来一个新的泄露面：429 的响应体若带上被限者的 IP / user id / Redis key，等于把限流实现细节和被限者身份交给攻击者。
- Decision：保持「429 先于 401」，并由两项测试固化：`test_anonymous_flood_is_throttled_before_authentication`（无 Token 洪水：401×3 → 429×2）与 `test_throttled_response_leaks_no_internal_identifiers`（429 体不含 user id、来源 IP、`taskflow` 前缀、堆栈）。
- Reason：①顺序上，「未认证流量也要受限」是限流有效性的前提——否则限流只对守规矩的客户端生效；②内容上，§48 明确要求错误信息不得泄露内部细节，429 同样是错误响应，没有豁免理由。
- Trade-off：客户端无法从 429 判断「自己是因为哪个身份被限的」。这是刻意的——该信息对攻击者有用、对合法客户端无用（客户端知道自己是谁）。

## Decision 025：TASK-047 定位为「整合验收」，先探测再写断言
- Problem：TASK-047 名为「限流测试」，但 TASK-046 已有 22 项细粒度测试。重复再写一遍既无收益，也会掩盖真正缺口。
- Decision：沿用 TASK-040 / TASK-044 的定位——**不重复细粒度断言**，只测「必须借助真实用户 + 真实业务端点 + 真实审计表 + 真实 Redis 键空间才能观察到」的跨模块性质。落地前先跑一次性探测脚本（10 个交叉面：跨端点配额、多用户隔离、换 IP、写副作用、审计、暴力破解、键命名空间与 TTL、匿名洪水、404 路径、响应体泄露），**据观测结果**决定写什么断言；脚本用完即删，不入库。
- Reason：①TASK-043/044 已证明「先探测再断言」能定位到真实缺陷，而凭推测写断言常常测了个空；②本轮探测确认十个面全部行为正确（未发现缺陷），因此 TASK-047 的产出是**契约固化**而非修复——价值在于让「按端点限流」「限流写审计」「去掉 TTL」「member 用固定串」这类改动立刻失败。
- Trade-off：契约固化型测试在「代码没变」时永远不会失败，看起来像没干活。因此本文件配套做了变异测试（4 个变异全部被杀死，见下），证明断言真实承重。
- **变异测试结果（TASK-047）**：①去掉 429 分支 → 13 failed；②身份维度退化为只用 IP → 3 failed（恰好是三项 user 隔离用例）；③去掉 `PEXPIRE` → 1 failed（键 TTL 用例）；④`member` 改用固定字符串 → 10 failed（含并发用例）。四个变异全部被杀死，还原后源码 blob hash 与 HEAD 逐字符一致。

## Decision 026：Celery Broker/Backend 均用 Redis，留空回落 `REDIS_URL`
- Problem：§21 规定 Redis 兼任 Celery Broker 与 Backend，但未给连接配置；是给 Broker/Backend 各配独立 URL，还是复用限流那个 Redis 实例？
- Decision：`celery_broker_url` / `celery_result_backend` 两个配置项**默认留空**，留空即回落到 `redis_url`。部署冒烟证明全链路可用（ping 任务 `SUCCESS`）。
- Reason：本项目规模（单机 compose、任务量以「每次用户操作几条通知」计）远未到需要独立 Broker 实例的程度；Redis 7 单实例处理限流 + 队列绰绰有余。留空的回落式设计保留隔离选项——出现瓶颈时改两个环境变量即可迁移，不用动代码。
- Trade-off：限流与队列共享实例，极端队列积压会挤占 Redis 资源拖慢限流。观察期内可接受；届时优先按 db 隔离（如 backend 用 db 1），再考虑独立实例。

## Decision 027：可靠性参数锁进测试——at-least-once 投递 + JSON-only
- Problem：规则 §8 要求异步任务考虑 retry / timeout / failure / idempotency。TASK-048 阶段还没有业务任务（TASK-049/050 才有），§8 在 App 层的落点是什么？
- Decision：把 App 级语义锁死并用 11 项测试钉住：①`task_acks_late=True` + `task_reject_on_worker_lost=True` + `worker_prefetch_multiplier=1` → **at-least-once 投递**（Worker 崩溃/被杀消息不丢、会重投）；②`task_soft_time_limit=300` / `task_time_limit=600` 双超时（软超时给任务清理机会，硬超时杀进程兜底）；③`accept_content=["json"]` 禁 pickle——pickle 反序列化即执行任意代码，任务消息所在 Redis 一旦被写入恶意消息就是 RCE；④`task_track_started=True` 区分排队/执行中。
- Reason：①§8 明言「不要假设 Celery 任务只执行一次」——App 层先承认 at-least-once，业务任务的幂等责任（TASK-049/050/051）才有明确前提；②JSON-only 是安全默认值，没有理由豁免；③超时数值规格未给（同 DECISIONS 015 的处理方式），取保守默认并允许 env 覆盖。
- Trade-off：at-least-once 意味着重复执行可能产生重复副作用，幂等负担在业务任务侧；JSON-only 意味着任务参数只能是可 JSON 化的标量/结构（本项目够用）。

## Decision 028：Celery 在 Redis 中的键统一挂 `taskflow:` 前缀
- Problem：TASK-045 键约定要求本项目所有 Redis 键以 `taskflow:` 开头；Celery 的 broker 队列键与结果元数据键默认不带前缀（如 `celery-task-meta-<id>`），会破坏「`taskflow:*` 之外的键都不属于本项目」的运维约定。
- Decision：broker 与 backend 均设 `global_keyprefix="taskflow:"`（`CELERY_KEY_PREFIX` 常量），部署冒烟实测所有键（含 `_kombu.binding.*` 与 `celery-task-meta-*`）都在前缀之下。
- Reason：一个实例上混着多个项目时（本机正是如此——6389 上曾有别的 Redis 实例），按前缀识别归属、按前缀清理是 TASK-045 已确立的纪律，Celery 不能例外。
- Trade-off：依赖 kombu 的 `global_keyprefix` 实现，属传输层选项而非 Celery 官方一等配置；已用容器冒烟实证生效，并用 `test_redis_key_prefix_applies_to_broker_and_backend` 锁住配置。

## Decision 029：notifications 表提前于 TASK-052 建模（用户确认）
- Problem：TASK-049「通知异步任务」在 TASK-052「Notification Model」之前，但 §24 的通知任务必须写 `notifications` 表才能谈重试与去重——表不存在则任务只能是空壳。
- Decision：经用户确认，把 TASK-052 的建模部分（Notification Model + Alembic 迁移）提前并入 TASK-049。沿用 TASK-058（Dockerfile）提前完成的先例；TASK-052 届时为检查项。建模按 §18 原文：id / user_id / type / title / content / is_read / created_at。
- Reason：①§24 三条要求（主业务失败不产生错误通知 / 失败可重试 / 重试不大量重复）全部依赖真实持久化，空壳任务无法实现也无法测试；②TASK-051 的幂等测试同理。
- 模型细化（§18 未定义处的补全）：`user_id` FK→users ON DELETE CASCADE（通知是"写给某用户"的内容，用户删除即失义；与 OperationLog 无外键形成对照——审计留痕、通知不留）；`type` String(50) 不加 CHECK（§18 列了四个场景但未定义为封闭枚举，TASK-053 收窄）；`content` 可空（title 摘要自足）；`is_read` NOT NULL 默认 false；索引 `(user_id, created_at)` 对应 `GET /api/v1/notifications` 的主访问路径。
- Trade-off：TASK-052 的独立性被削弱；迁移链上 TASK-049 的提交包含建模变更，回滚 TASK-049 需连带迁移。

## Decision 030：通知任务的幂等 = 先插库、后写 Redis 完成标记
- Problem：at-least-once 投递（DECISIONS 027）下，通知任务可能被重试/重投递多次；§24 要求「重试不会产生大量重复通知」。去重标记放哪、先写谁？
- Decision：调用方为每次通知派发生成唯一 `idempotency_key`（uuid4，同一业务事件的重试/重投递共享）；任务执行时先查 Redis `taskflow:notify_done:<key>`（存在即跳过），插库成功**之后**再 `SETNX` 写标记（TTL 7 天）。顺序刻意为「先 DB 后 Redis」：DB 是事实源——反过来（先标记后插库）在"标记后崩溃"时丢通知，而现顺序的崩溃窗口最多产生一条重复（§24 只约束"不大量重复"）。Redis 故障 fail-open（只损失去重，不丢通知）。
- Reason：①去重键必须由调用方生成且跨重试稳定——Celery `self.retry` 会换新 task id，用 task id 做幂等键在重试链上失效；②notifications 表按 §18 没有 idempotency 字段，不为去重私加列，Redis 标记（本就是 Broker/Backend 宿主，§21）是零侵入方案；③`taskflow:notify_done:` 沿用 TASK-045 键约定。
- Trade-off：崩溃窗口的单条重复；TTL 过期后同一 key 再重投会重复（7 天远超任何合理重投窗口）；并发重投的检查-插入竞态最多多一条。
- 配套：Celery worker 是同步上下文，async 客户端不可用（命令返回协程）——`app/db/redis.py` 补充同步入口 `get_sync_redis_client()`（同一 URL、同一 socket 超时纪律）；任务内 DB 写入用每次调用独立事件循环 + 短命 engine（asyncpg 连接池绑定事件循环，跨 loop 复用必报错，不能共享 API 进程的 engine 单例）。

## Decision 031：操作日志归档 = 迁入 operation_logs_archive 表（用户确认）
- Problem：§23 把「归档操作日志」列为 Celery 后台任务，但没定义「归档」动作——是直接删除超期日志，还是迁到归档表？
- Decision：经用户确认，**把超过保留期的 operation_logs 行迁入 `operation_logs_archive` 历史表**（新建表 + Alembic 迁移 `524ab172e659`，`upgrade head` 实证落库），主表瘦身、审计历史完整保留，最贴合「归档」字面。保留期 `log_archive_retention_days` 默认 90 天、可经 `.env` 覆盖。
- Reason：①审计日志价值在可追溯，直接删除违背其存在意义（user_id 无外键本就是为审计独立）；②归档表与原表同构（user_id / resource_type / resource_id / action / payload / created_at 原样搬入），加 `archived_at` 记录迁移时间，可承担原表的全部查询语义。
- 模型细节：`operation_logs_archive.id` **复用原日志 id 且 `autoincrement=False`**——归档是「同一条记录搬家」不是「新建记录」。复用 id 让两表按 id 直接对账，并为任务幂等提供去重点（见 DECISIONS 032 配套）。
- Trade-off：归档表随保留期增长需独立治理（未来可再加二级归档/冷存储）；保留期是运维参数，给默认 + 可配置，不猜业务规则（规则 §3）。

## Decision 032：附件清理 = 回收孤儿物理文件（用户确认），加 mtime 年龄窗口
- Problem：§23「清理过期附件」未定义「过期」判定；TASK-042 模型注释已明确「任务级联删除只清 attachments 记录，物理文件由清理任务回收」。孤儿 vs 按时间的两种解读如何取舍？
- Decision：经用户确认，**清理 = 扫描 storage 卷，删除 DB 的 `attachments` 表无对应 `storage_path` 记录的物理孤儿文件**（契合 TASK-042 注释的责任划分，且绝不误删在用的附件）。加 `attachment_orphan_min_age_seconds`（默认 3600）年龄窗口：仅当文件 mtime 早于 `now - min_age` 才删，给正常删除流程留竞争缓冲，避免误删「正在上传（先落盘后落库）」或「刚删任务尚未回收」的文件。批大小 `maintenance_batch_size`（默认 1000）。
- Reason：①孤儿来源单一且明确——任务删除触发 attachments 记录 CASCADE，物理文件遗留，本任务回收，闭环完整；②按时间清「已完成任务的附件」会删仍在库中的有效记录，风险更高且语义更模糊，故不采用；③年龄窗口是「不误删进行中文件」的工程护栏，非业务规则。
- 安全性（§9）：只用 `LocalStorageBackend`（唯一做相对 key→绝对路径解析、且保证不越出存储根的地方）；删除前 `validate_key` 二次校验拒绝穿越/非法 key（双保险）；`backend.delete` 幂等（`missing_ok`），重投递再扫一遍时孤儿已不在 → no-op。

## Decision 033：TASK-051 把「重试/幂等/失败」从声明层推到行为层（纯测试）
- Problem：TASK-049/050 只断言了 `autoretry_for` 元组与「同幂等键第二次调用返回 skipped」——这是**声明层**。声明正确 ≠ 故障下真生效：Celery 真会在瞬态故障后重跑吗？超 `max_retries` 后真抛错吗？参数错误真在触达 DB 前短路吗？这些都没被验证过。
- Decision：TASK-051（纯测试，不动应用代码）新增 `tests/test_task_resilience.py` **8 项**，把三个业务任务放进**真实故障场景**：①用 monkeypatch 让 `_insert_notification` 首跑抛 `SQLAlchemyError`、次跑成功 → 经 eager 模式 `delay()` 验证「真的重跑且恰好 1 行」；②让它永远失败且 `max_retries=2` → 验证「真的抛错、`_insert_notification` 被调用 3 次、零通知行」（§8 failure / §24 要求 1）；③非法参数 → 验证「`_insert_notification` 0 次调用、0 重试、0 行」（短路先于 DB）；④`archive` / `cleanup` 经 `delay()` 任务机端到端（此前只测直接调用）；⑤清理重跑 → 0 删除 0 错误（重投递幂等）；⑥三任务各跑两遍 → 累计副作用 = 单跑一遍（整体 at-least-once 安全整合验收）；⑦三个业务任务都不覆盖 App 级 `soft/hard_time_limit`（§8 的 300/600s 不被装饰器旁路）。
- Reason：①TASK-040/044/047 已确立「声明层测过、行为层/整合层才暴露真问题」的先例，重试与幂等恰是最容易「声明正确、故障下崩」的两种机制；②维护任务此前绕过了 Celery 任务机直接当函数测，eager 派发才验证「任务真的注册进 Worker 能跑」；③超时不被绕过是 §8 的安全底线，只有钉成测试才不会被顺手改掉。
- Trade-off：①eager 模式用同步重试，把 backoff/jitter 关掉让测试即时（不测退避数值，只测「会重试 / 会耗尽」语义）；②`max_retries` 在测试内临时降到 2，避免耗尽路径被 1+2+4+8+16s 退避睡死——还原在 `finally`，不污染全局；③`hard_time_limit` 未显式设置时不是任务对象属性（访问抛 `AttributeError`），断言改用 `getattr(task, "hard_time_limit", None) is None` 判定「未覆盖」。

## Decision 034：TASK-052 建模检查项 = 补 Notification Model 测试，固化 §18 完整性
- Problem：DECISIONS 029 把 TASK-052 的建模（Notification Model + 迁移 `b7d2e9a4c6f8`）提前并入 TASK-049，并明确「TASK-052 届时为检查项」。但 TASK-049 提前建模时只写了「通知任务测试」（`test_notification_task.py`，覆盖落库/幂等/重试/FK 级联），没有「通知 Model 本身」的专项测试——而每个独立 Model TASK（TASK-021/026/031）都含离线模型测试，此处留下真实缺口。
- Decision：TASK-052 不产生新应用代码，补 `tests/test_notification_model.py` **16 项**，把「建模完整性」固化为可回归测试：①离线（不连 DB）钉死 §18 七字段集合、各列类型/可空性/长度、`user_id` FK→users ON DELETE CASCADE 且单列索引、`is_read`/`created_at` 的 server_default、`(user_id, created_at)` 复合索引、`__repr__`；②DB 集成（真实 5433）验证七字段 roundtrip、`content` 可空、`is_read` 默认 false、`created_at` 自动、删用户 CASCADE 清通知、按接收人查询主访问路径。
- Reason：①这是 DECISIONS 029「检查项」的最佳落地——用测试把「建模是否仍符合 §18」变成可回归断言，而非一次性肉眼核对；②对齐 Model TASK 惯例，填补提前建模遗留的缺口；③纯 Model 层，不碰 TASK-053 的 Service/API、TASK-054 的已读/未读、TASK-055 的端到端测试，边界清晰。
- Trade-off：索引存在性用 model 层离线断言钉死（与 TASK-026 同），未再查 `pg_indexes` 物理表——model 层 Index 定义已等价于 DDL。

## Decision 035：通知端点仅认证不加功能级权限（TASK-053）
- Problem：§18 通知写给「某个用户」、与登录身份强绑定；通知端点（`GET /notifications`、`PATCH /notifications/{id}/read`）要不要套 §6 的功能级权限（如 `notification:read`）？
- Decision：通知端点**仅认证**（依赖 `CurrentUser`），不加功能级权限依赖。
- Reason：①通知是用户私有收件箱，任何已认证用户访问自己的是天然合理的，无对应业务语义需要 `notification:*` 闸门；②§6 权限清单根本无 `notification:*` 项，要加须改 RBAC seed（新增角色权限绑定），超出本 TASK 范围且引入无业务价值的权限项；③最小权限原则下「不加多余的权限闸门」优于「为每个端点机械套用 `require_permission`」。
- Trade-off：若未来出现「管理员代看他人通知 / 全局通知广播」等需求，再单独加 `notification:*` 权限项与对应资源级判定；届时服务水平隔离（仅自己）仍由 Service 层按 `user.id` 强制，权限依赖只做「能否访问收件箱」的粗粒度开关。
- 实现落点：`app/services/notification.py` 模块 docstring 记录该决策；Service 层 `list_user_notifications` / `mark_notification_read` 都按 `user.id` 过滤，非接收人 / 不存在 → 404 同文案（`Notification not found`），IDOR 防枚举；Router 仅声明 `CurrentUser`，不引 `require_permission`。
- 配套（幂等）：归档与清理都天然幂等，匹配 at-least-once（DECISIONS 027）——归档靠「id 复用 + `pg_insert ... ON CONFLICT (id) DO NOTHING` + 同事务删主表」，重投时主表可搬行已不在、归档表已存在 → no-op；清理靠「删文件幂等 + 孤儿判定只读 DB」。

## Decision 036：read-all 响应体返回标记条数 `{"marked": N}`（用户确认，TASK-054）
- Problem：§25.8 只定义了 `PATCH /notifications/read-all` 端点路径，未定义响应体——返回空成功体、更新后的列表、还是统计信息？
- Decision：经用户确认，响应 `{"data": {"marked": N}}`，N = 本次真正从已读翻转为已读的条数（已是已读的不计入）。
- Reason：①信息量最大——前端调一次即可同步未读角标，无需再查 `GET /notifications`；②天然幂等——重复调用返回 0，客户端可用 N 判断是否有实际变化；③返回全量列表（备选方案）与 `GET` 端点职责重叠且响应体可能很大，不采用。
- 实现落点：CRUD 用单条 `UPDATE ... WHERE user_id = :uid AND is_read = false`（只命中未读行，`rowcount` 即真翻转数，SQL 层限定自己的收件箱——资源级隔离）；空收件箱 → 200 `marked=0`（「没有未读」是合法的 0，不是 404）；`/read-all` 刻意声明在参数化路由 `/{notification_id}/read` 之前，消除路径解析歧义（两段路径本无实际冲突，防御性排序）。

## Decision 037：结构化日志 = 环境推导格式 + 出口自动脱敏 + 全路径访问日志（用户确认，TASK-056）
- Problem：§33 只说「使用 Python logging」「生产环境采用结构化日志格式」，未定义：①开发环境用什么格式？②§33 的「禁止输出 password/token」靠什么保证？③path/method/status_code/duration 四个字段怎么采集（端点内看不到总耗时与最终状态码）？
- Decision（三项均经用户确认）：①**格式按环境推导**——`APP_ENV=production` → JSON、其余 → 人读文本，可用 `LOG_FORMAT=json|text` 显式覆盖（`auto` 为默认）；②**加出口自动脱敏过滤器**（`SensitiveDataFilter`），不依赖开发者自觉；③**访问日志用中间件记录全部路径**（含 `/health`、`/docs`、`/`），`LOG_REQUESTS=false` 可整体关闭。
- Reason：①§33 只强制生产结构化，本地文本格式排障效率更高，且 `LOG_FORMAT` 让「本地/线上一致」也能按需达成；②硬禁止项靠约定必然会被一次 `logger.info(f"login {token}")` 击穿，出口统一脱敏是唯一可靠位置；③路径全记保证可观测性完整（探针请求同样有排查价值），噪声问题交给开关而不是默认裁剪信息。
- 实现落点：`app/core/logging_config.py`（`request_id_var` / `user_id_var` 两个 ContextVar；`JsonFormatter` / `TextFormatter`；`SensitiveDataFilter`；幂等的 `configure_logging()`）+ `app/core/middleware.py` 的 `RequestLoggingMiddleware` + `app/main.py` 接线（日志先于应用创建配置；访问日志注册在限流**之后**，使其处于更外层，`duration` 才是客户端实际等待时间）。
- Trade-off：不做第三方依赖（python-json-logger）——stdlib `Formatter` + `json.dumps` 足够，符合规则 §15「不增加无意义技术」；`JSONFormatter` 用 `default=str` 降级非原生类型，宁可格式化为字符串也不丢日志。
- 边界：§34 的 `request_id`（生成 / 客户端透传 / 响应头）属 TASK-057，本 TASK 只建好字段通道（无值时输出 `null`，保持 schema 稳定）。
- **本 TASK 实测发现并修复的 2 个真实缺陷**（均由新测试捕获，非推测）：
  1. **脱敏过滤器会吃掉 `%s` 占位符 → 整条日志丢失**。初版对 `record.msg` 一律做文本脱敏，`logger.info("token=%s", token)` 的模板被改成 `"token=***"`，`getMessage()` 随即抛 `TypeError: not all arguments converted`；logging 吞掉该异常，日志**静默消失**（只在 stderr 留一行 "--- Logging error ---"）。修复：有 `args` 时**只脱敏 args**（模板原样保留），无 `args` 时才脱敏 msg。
  2. **访问日志的 `user_id` 恒为 `null`**。初版在 `finally` 里先还原 ContextVar、之后才写日志，导致**每个成功请求**的访问日志都丢掉 user_id——正是 §33 要求必须携带的字段。修复：改用 `try/except/else/finally`，在 `else` 分支（日志写入后）才返回、`finally` 负责还原。
  3. **每个请求产生两条访问日志**（真实容器冒烟发现，pytest 测不出——探针应用没有 uvicorn）。`configure_logging` 把 uvicorn 三个 logger 收编到 root 后，`uvicorn.access` 那行也走本项目的 formatter 输出了，与 `RequestLoggingMiddleware` 的日志重复，且它不含 duration/user_id。修复：把 `uvicorn.access` 级别压到 WARNING（例行访问行不再输出，异常日志保留）。
- **附带效应（已知、可接受）**：`db/session.py` 用 `echo=settings.debug` 打开 SQL echo，此前 root 无 handler 因而 SQL 日志不可见；本 TASK 安装 handler 后**开发环境的 SQL 语句日志会真正输出**（debug=True 的既有意图得以生效）。生产 `DEBUG=false` 时不输出。
- 测试环境教训：**pytest 默认把 root logger 级别设为 WARNING**，因此断言 INFO 级日志必须给目标 logger 显式 `setLevel(INFO)`，否则会得到「空输出」并可能让「开关关闭」类断言**假通过**（本 TASK 的两个用例已按此修正）。测试套件默认 `LOG_REQUESTS=false`（conftest autouse，与 `rate_limit_enabled` 同套路），访问日志自身的测试在用例内打开。

---

## Decision 038：Request ID = 单一 `X-Request-ID` 头 + 白名单校验 + 独立最外层中间件（用户确认，TASK-057）
- Problem：§34 只规定「每个 HTTP 请求生成 `request_id`」「可由客户端传入或服务端生成」「日志中必须带」，未定义：①用哪个 HTTP 头？②客户端传入的值能否信任？③要不要写进错误响应体？④生成逻辑放哪里？
- Decision（三项经用户确认 + 一项工程决策）：①头名统一 **`X-Request-ID`**（传入与回传同名，不作多头兼容）；②客户端传入值**经白名单 `^[A-Za-z0-9._-]{1,64}$` 校验后才接受**，不合法则丢弃并服务端生成；③`request_id` **不进入**错误响应体（§26 信封保持 `{"detail": ...}`），只走响应头；④工程决策：**独立的 `RequestIdMiddleware`，注册在最外层**（与 `LOG_REQUESTS` 开关解耦）。
- Reason：①头名越少歧义越少，`X-Request-ID` 是事实标准；②原样信任客户端值会同时打开三个口子——**日志注入**（值里带 `\n` 可伪造整条日志行，污染审计）、**日志膨胀**（几十 KB 的 id 撑爆每行日志）、**身份伪造**（id 是可观测性的信任锚，可随意设定则失去排查价值），64 字符 + 白名单足以容纳 UUID/ulid/ksuid/hex/traceparent 全部主流形态；③§26 信封已被前端依赖，为一个排障字段改契约不划算（响应头已足够）；④若把生成逻辑塞进访问日志中间件，`LOG_REQUESTS=false` 时就不再生成、响应头也没了——§34 的硬要求会被一个**日志开关**悄悄破坏；而「必须最外层」是因为 request_id 要出现在本次请求的**所有**日志上（含限流中间件的 warning 与访问日志本身）。
- 实现落点：`app/core/middleware.py`（`REQUEST_ID_HEADER`、`resolve_request_id()`、`RequestIdMiddleware`）+ `app/main.py`（**最后**注册 → 最外层，嵌套为 `RequestId → RequestLogging → RateLimit → 路由`）。
- Trade-off：不为 `traceparent`（W3C 分布式追踪）做专门解析——它落在白名单内可原样透传，链路已足够串联；真正的 span 上报属于观测平台，不在本项目范围（§15）。
- 已知边界（有意接受）：未处理异常由 Starlette 的 `ServerErrorMiddleware` 渲染 500，而它在最外层**之外**，故该响应**没有** `X-Request-ID` 头（要修就得自己渲染 500，等于与框架的错误中间件重复）。这不影响 §34：该请求的日志里仍带着 request_id。已写成测试固化这个边界。
- 测试发现（非实现缺陷，但暴露了测试写法的失真）：HTTP 头的值在协议层是 **latin-1** 字节并由 Starlette 按 latin-1 解码，因此「客户端传 `中文id`」在中间件眼里是一串 latin-1 乱码（`ä¸æ–‡id`）。初版测试辅助函数用 latin-1 编码值，遇到非 ASCII 直接抛 `UnicodeEncodeError`——等于**永远测不到这条路径**。改为按 UTF-8 编码为原始字节（忠实模拟线上字节），白名单正好拦住这种乱码形态。

## Decision 039：生产 compose 用独立完整文件 + 端口内外分离 + 密钥 fail-fast（用户确认，TASK-059）
- Problem：§4 文件清单要求 `docker-compose.prod.yml`，但开发文档只定义了**开发环境** compose（§29：postgres/redis/api/celery_worker，nginx 可选）与「生产推荐 Client→Nginx→Gunicorn+Uvicorn Worker」（§31），没有规定生产 compose 的形态与约束：①独立完整文件还是覆盖文件？②哪些端口对宿主暴露？③必需密钥缺失时怎么办？④nginx 是否在本 TASK 引入？
- Decision（四项经用户确认）：①**独立完整文件**（不采用 `-f docker-compose.yml -f docker-compose.prod.yml` 覆盖式），单独 `-f docker-compose.prod.yml` 启动；②**端口内外分离**——postgres / redis **完全不发布宿主端口**，app 只绑 `127.0.0.1:${APP_PORT:-8000}`（对外暴露由 TASK-060 的 Nginx 承担）；③必需密钥（`JWT_SECRET_KEY`、`POSTGRES_PASSWORD`）用 `${VAR:?}` 必填语法，**未设置或为空即拒绝启动**；④nginx / Gunicorn / Uvicorn worker 留给 TASK-060，本 TASK 只做四服务的生产化。
- Reason：①compose 的合并语义对 `ports` 是**拼接而非覆盖**，因此「用覆盖文件删掉开发版发布的 5433/6389」做不到——那会让生产库直接暴露在宿主上；独立文件才能保证暴露面可控，代价是四服务定义要维护两份。②Redis 未配 `requirepass`、数据库也不该对外，发布端口等于敞开；app 绑回环既符合「只有 Nginx 对外」的拓扑，又让本 TASK 仍能直接冒烟（用 `APP_PORT` 避开开发栈占用的 8000）。③生产最怕的不是启动失败，而是**带着 `change-me` 默认密钥静默上线**（等于公开 Token 签发权），`${VAR:?}` 把配置缺失变成启动期硬错误。④规则 §13：一次只执行当前 TASK。
- 同一 TASK 内的配套决策（都与「生产真实性」直接相关）：
  - **独立 compose 项目名 `taskflow-prod`**：卷 / 网络 / 容器名都带前缀。开发版没有顶层 `name`，项目名回落为目录名——若生产沿用同名，在开发机上启动生产栈会连到 `task-flow_postgres_data`（开发库），是最危险的一类「看起来正常」的串用。
  - **不设 `container_name`**：固定容器名既与开发栈同名容器冲突，也阻碍扩容。
  - **`DEBUG=false`**：`Settings.debug` 同时驱动 SQLAlchemy `echo` 与 FastAPI debug，生产开着会把每条 SQL 写进日志（§9 敏感日志）。
  - **容器日志轮转**（json-file `max-size=10m` / `max-file=3`）：不轮转的容器日志会一直增长到写满宿主磁盘。
  - **Redis 开启 AOF**（`--appendonly yes`）：Redis 同时是 Celery Broker（§21），不持久化则容器重启即丢队列中的任务。
  - **`restart: always`**（开发版是 `unless-stopped`）+ **`stop_grace_period: 30s`**：给在途请求 / 任务收尾时间；任务本身幂等（TASK-051 / §24），即使超时被强杀，重投也无重复副作用。
  - **禁止 `env_file: .env`**：宿主 `.env` 的 `DATABASE_URL` / `REDIS_URL` 指向 `127.0.0.1:5433` / `127.0.0.1:6389`（宿主端口），注入容器会覆盖掉 compose 里正确拼好的容器内地址（服务名 `postgres` / `redis`），容器将连不上任何东西。已写成测试禁掉。
- 同步修正的既有缺口（本 TASK 暴露）：本地 `.env` 缺 `POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB`——它一直供**宿主机**运行使用，compose 靠默认值兜底，所以此前从未暴露；生产 compose 要求它必须有值。`.env.example` 补 `DEBUG` 项与生产必填说明；`requirements.txt` 补 `PyYAML`（生产 compose 契约测试要解析 YAML，否则 TASK-061 的 CI 会因缺包失败）。
- Trade-off：生产栈与开发栈的服务定义有两份，存在漂移风险；已用 `tests/test_prod_compose.py` 的「生产服务集合 = 开发服务集合 + 生产化约束」交叉校验兜住。
- 已知边界（有意接受）：`${VAR:?}` 只能拦「未设置 / 为空」，**拦不住「设置成了弱值」**（例如把 `POSTGRES_PASSWORD` 填成 `postgres`）。后者靠部署文档与 `.env.example` 提示；若要强制，需要在应用启动时做密钥强度校验，不在本 TASK 范围。
- **TASK-060 更新**：本决策第 ② 条里「app 只绑 `127.0.0.1:${APP_PORT:-8000}`」已被取代——接入 Nginx 后 app 的宿主端口被**整体去掉**（原因见 Decision 040）。`${APP_PORT}` 随之退役，对外端口改由 `${NGINX_HTTP_PORT}` 控制。

## Decision 040：Nginx 接入——入口收敛为唯一反代；§31 的「静态附件访问」实现为**不直出**（用户确认，TASK-060）
- Problem：§31 规定了生产链路 `Client → Nginx → Gunicorn → Uvicorn Worker → FastAPI`，并列出 Nginx 的五项职责（反向代理、请求体大小限制、基础超时、**静态附件访问**、基础安全 Header），但没有规定：①Nginx 以容器还是宿主进程形式部署？②app 是否还保留宿主端口？③「静态附件访问」怎么实现？④是否包含 TLS？其中 ②③ 直接决定安全边界。
- Decision（四项经用户确认）：
  1. **Nginx 是容器服务，且是唯一对外入口**：新增 `nginx` 服务（`nginx:1.27-alpine`）发布 `${NGINX_HTTP_PORT:-80}:80`；app 从 prod compose 中**摘掉宿主端口**（TASK-059 的 `127.0.0.1:8000` 一并删除），只在 compose 网络内以服务名 `app:8000` 可达；
  2. **附件不由 Nginx 直出**：保持「API 鉴权后返回文件流」，nginx 只反代；
  3. **仅 HTTP 80**：TLS 由上游负载均衡终止，证书不进仓库；
  4. 配套：固定 compose 子网 `172.28.0.0/24`，与 `TRUSTED_PROXY_IPS` 严格对应。
- Reason：
  1. **去掉 app 的宿主端口才让「真实客户端 IP」这件事可解**：留在宿主（哪怕只绑回环）就意味着同机任何进程都能直连应用并自带 `X-Forwarded-For`。去掉之后，「客户端无法绕过 Nginx 的覆盖写入」从**约定**变成**结构保证**——这是 Decision 042 那套信任模型能够成立的前提。同时 app 不再需要 `APP_PORT`，暴露面收敛到一个端口。
  2. **§31 的「静态附件访问」若按字面用 `alias`/`root` 映射附件卷，等于删掉 TASK-043 的鉴权**：附件下载有功能级 `attachment:download` + 资源级归属链（不在链上 404 防枚举）。直出之后任何知道路径的人都能下载任意附件（教科书式 IDOR）。因此本 TASK 的选择是「不做直出」，并把理由写在 `nginx/nginx.conf` 顶部。性能上的正确下一步是应用鉴权后返回 `X-Accel-Redirect` 交由 nginx 读卷（鉴权不丢），但那要改动 TASK-042/043 的下载端点，属新增功能，须有文档依据再做（规则 §3/§5）。
  3. §31 未要求 TLS；把自签证书提交进仓库是反面实践（私钥进版本库），而生产证书应由 ACME/负载均衡管理。同时因此**不发 HSTS**：在纯 HTTP 响应上发它既不被浏览器采纳，还会误导排查者以为已启用 TLS。
  4. 见 Decision 042——信任网段必须是一个**确定事实**，不能靠 Docker 随机分配。
- 同一 TASK 内的其他部署决策：
  - **请求体大小限制做成「粗粒度外圈」**：`client_max_body_size 12m` **严格大于**应用的 `MAX_UPLOAD_SIZE`（10 MiB）。颠倒过来的后果是超限上传拿到 nginx 的 HTML 错误页而不是 §26 的 JSON 信封，客户端无法统一处理；留余量还让 `MAX_UPLOAD_SIZE` 调大时不必同步改 nginx（避免两处漂移）。
  - **`proxy_set_header Host $host`**（而非 `$http_host`）：后者会把客户端任意 Host 头透传给应用。
  - **`server_tokens off`**、三个安全 Header 带 `always`（否则 4xx/5xx 不带）。
  - **nginx 健康检查探 `location = /nginx-health`**（只回答「代理能提供 HTTP」，不依赖上游）：若探 `/health`，应用重启期间 nginx 也会被标记为不健康，「入口挂了」与「后端重启中」两件事混在一起，反而更难排查。
  - **配置以只读方式挂载**（`./nginx/nginx.conf:/etc/nginx/nginx.conf:ro`）：它是**部署配置**而非应用源码，不违反「生产不挂宿主源码目录」；契约测试用显式白名单（`ALLOWED_HOST_MOUNT_SUFFIXES`）表达这个例外，而不是放宽整条规则。
- Trade-off：①多一跳（客户端 → nginx → app），换来的是鉴权与可观测性；②容器化 nginx 的配置变更需要 `up -d`（compose 检测到挂载文件变化会重建容器）；③附件下载流量仍要经过应用进程（不做 X-Accel-Redirect 的性能优化）——对当前规模是合适的取舍。
- 验证方式（冒烟实测，见 TESTING 的 TASK-060 章节）：`docker port` 实证只有 nginx 对外；宿主能访问 nginx 的 80 端口；`docker compose` 里除 nginx 外无任何 `ports` 条目（契约测试固化）。

## Decision 041：Gunicorn 进程模型——worker 数走环境变量、不开自带访问日志（TASK-060）
- Problem：§31 要求生产用 Gunicorn + Uvicorn Worker，但没有给出任何参数：worker 数多少？超时多长？访问日志怎么处理？§30 只要求 Dockerfile 有「合理的启动命令」。
- Decision：
  1. 启动命令由 prod compose 覆盖（`command:`）而不是改 Dockerfile 的 `CMD`——与 `celery_worker` 已在用的模式一致，且**开发栈行为零变化**（同一个镜像既跑开发也跑生产）；
  2. `--worker-class=uvicorn.workers.UvicornWorker`、`--workers=${WEB_CONCURRENCY:-2}`（规格未给数值，取 2 并可经 `.env` 覆盖，与 DECISIONS 015 对限流阈值的处理同一思路）；
  3. `--timeout=60`、`--graceful-timeout=30`（与 compose 的 `stop_grace_period: 30s` 对齐，避免 SIGTERM 后在途请求被 compose 提前强杀）、`--keep-alive=5`；
  4. **不开 `--access-logfile`**：访问日志已由应用的 `RequestLoggingMiddleware` 按 §33 记录（含 `request_id` / `user_id` / `duration` / `client_ip`），再开一份 Gunicorn 的会重复输出。
- Reason：①`uvicorn.workers.UvicornWorker` 让每个 worker 是 ASGI 异步进程，能在单个进程内并发处理请求（裸 `uvicorn` 单进程只能吃满一个核，是开发用配置）；②worker 数涉及 CPU 核数、内存与 Postgres 连接池的权衡，**属于部署配置而不是代码逻辑**，放进 `${WEB_CONCURRENCY}` 让运维可按机器调整，不在代码里写死；③重复访问日志这条是 TASK-056 的实测教训（当时 uvicorn 的 `uvicorn.access` 与应用中间件各出一条，只能靠容器冒烟发现，pytest 测不出）——所以这里**预先**避免，并写成契约测试 `test_gunicorn_access_log_is_not_duplicated`。
- 前置核实：`uvicorn.workers.UvicornWorker` 在 uvicorn 0.52.4 中仍可用（容器内实测导入成功）；注意该模块依赖 `fcntl`，在 **Windows 宿主上无法导入**——这也是 Gunicorn 只能跑在容器（Linux）里的原因之一，宿主机上的 pytest 因此不直接测 Gunicorn 进程本身，而是测 compose 契约 + 容器冒烟。
- Trade-off：Gunicorn master 自身的启动日志仍是纯文本（它用自己的 logger，不经应用的 formatter），与 §33 的 JSON 格式不统一。这是刻意接受的：§33 约束的是**应用日志**，而 master 的启动/退出信息属于基础设施层（与 nginx 的日志同类）。若将来要统一，需自定义 `--logger-class`，属过度工程。

## Decision 042：反代后的客户端真实 IP——覆盖式头 + 信任网段 + 配置错误向安全侧退化（TASK-060）
- Problem：DECISIONS 018 在 TASK-046 就写下了一条遗留约束：「Nginx 后所有请求的 `client.host` 都是 Nginx 的地址，IP 维度会退化为**所有匿名用户共享一个配额**。这一点在 TASK-060 接入反代时**必须**一并解决」。现在到了必须解决的时候，而显然的两种极端都不能接受：无条件信任 `X-Forwarded-For`（攻击者随手改值就把限流拆成无限份，审计日志也不可信）；完全不信任（IP 维度限流形同虚设）。
- Decision（用户确认）：
  1. **Nginx 侧**：`proxy_set_header X-Forwarded-For $remote_addr;` —— **覆盖**写入，而不是会追加的 `$proxy_add_x_forwarded_for`；
  2. **应用侧**新增两个设置：`TRUST_PROXY_HEADERS`（默认 **false**）与 `TRUSTED_PROXY_IPS`（逗号分隔 IP/CIDR）。**三条同时成立**才采信：开关开启、TCP 对端落在信任网段内、该头恰好是**一个**合法 IP；
  3. **配置错误向安全侧退化**：开关打开但网段为空/全非法 → **不采信**（而不是「信任任何人」）；
  4. **关掉 ASGI 侧的改写**：prod compose 里 `FORWARDED_ALLOW_IPS=""`，让 `app/core/client_ip.py` 成为客户端 IP 的**唯一**判定点。
- Reason：
  1. 应用侧单独校验是不够的——「值得信任的头」必须由反代**覆盖**写入来保证。若用追加语义，客户端自带 `X-Forwarded-For: 1.2.3.4` 会排在链首，即使应用侧「取第一个」也照样被骗。两层配合才完整：反代保证**内容不可伪造**，应用保证**来源必须是它信任的代理**。
  2. 默认关闭 + 网段必填，让**未配置的环境（含全部现有测试）行为与 TASK-046 完全一致**，不引入任何隐式信任。这条对「不破坏既有 22+ 限流测试」也是必要的。
  3. fail-safe 的方向选择是刻意的：配置错误应该退化成「安全但限流不准」（所有匿名用户仍共享配额），而不是「限流可被无限拆分」。前者是被动挨打，后者是主动开门。
  4. 两处逻辑叠加是排障噩梦：uvicorn 的 proxy-headers 默认信任 `127.0.0.1`，一旦有人把应用放到本机反代之后，`request.client.host` 就会**在应用不知情的情况下**变成转发头里的值。显式置空等于把「谁决定客户端 IP」这个问题收敛到一个地方。
- 配套实现细节：
  - **只认单一 IP 值**：本项目拓扑是单层反代，出现多值说明有环节在追加（或客户端自己塞的），一律不采信并回落到对端地址（同样是 fail-safe 方向）。
  - **IPv4-mapped IPv6 归一**（`::ffff:172.28.0.5` → `172.28.0.5`）：某些容器网络栈会用这种形式表示 IPv4 对端，若不归一，`in IPv4Network` 恒为假，会出现「配置看起来对、信任却永远不生效」的**静默**失效。此缺陷由本 TASK 的测试捕获（初版只归一了采信路径，回落路径漏了，日志里会混进 `::ffff:` 前缀）。
  - **固定 compose 子网 `172.28.0.0/24`**，并与 `TRUSTED_PROXY_IPS` 严格对应：靠 Docker 随机分配地址段会让信任判定时灵时不灵；契约测试对两处值做**交叉校验**（改一处不改另一处会直接失败）。
  - **访问日志增加 `client_ip` 字段**：反代之后若只记 TCP 对端地址，日志里所有请求都来自 Nginx，排查时没有区分度；记录解析后的真实 IP 才让「限流为什么打到这个用户」可复盘。**注意新增字段要同时改 `TextFormatter` 的白名单**：文本格式对额外字段是白名单渲染（防止任意 `extra=` 撑爆日志行），只加进 `extra={...}` 的话该字段**只在生产 JSON 里存在**——开发环境看不到，而开发环境恰恰是人看日志的地方。这个缺口 pytest 测不出（用例只断言 JSON 负载），是开发容器冒烟发现的；已补白名单 + 专项断言。
- Trade-off：①`TRUSTED_PROXY_IPS` 是一个需要运维正确配置的旋钮，配错会静默退化成共享配额——已用契约测试（compose 子网交叉校验）+ fail-safe 语义 + DEPLOYMENT 文档三重兜住；②多值一律拒绝意味着将来若在前面再加一层代理（CDN），需要重新审视此决策（会先表现为限流不准，而不是安全失效）。

## Decision 043：CI 门槛取「只抓缺陷、不碰风格」，并把「测试硬编码的端口」当成 CI 的契约（TASK-061）
- Problem：§44 只规定「至少执行：安装依赖 → lint → pytest → docker build」，没有规定 lint 用什么工具、门槛多高、是否强制格式化、`docker build` 做到哪一步。而有三条硬约束是文档没写、但不定就会出错的：①测试套件里 **40 个文件把 `127.0.0.1:5433` / `127.0.0.1:6389` 写成模块级常量**（历史原因：本机 5432 被另一个 PostgreSQL 占用），CI 必须决定是让 service 去适配测试还是反过来改测试；②lint 规则集若不写死，同一份代码在**不同 ruff 版本**下结论不同（实测：不写 `select` 报 219 项、写成本仓库的规则集报 36 项），门禁会变得不可复现；③`.env` 不入库，CI 里 `Settings` 只能从环境变量取配置，而它的默认值是 compose 服务名（`postgres:5432` / `redis:6379`），在 runner 上无法解析。
- Decision（用户确认）：①lint 门槛 = ruff **经典默认规则集** `E4/E7/E9/F`（不引入 `I` / `UP` / `B` / `S`）；②**不启用 `ruff format`** 作为格式门禁；③CI **包含迁移可逆性验证**（`upgrade head → downgrade base → upgrade head`，§37）；④`docker build` **只构建应用镜像、不推送**。此外两条由约束直接推出：⑤service 端口映射为 **5433 / 6389**（适配测试，而不是改 40 个测试文件）；⑥ruff **版本与规则集都钉进仓库**（`ruff==0.16.7` + 显式 `select`）。
- Reason：
  1. 选 `E4/E7/E9/F` 的理由是**它们报的是缺陷而不是风格**：本仓库在该规则集下的 36 项全部是真实问题（未用导入、重复导入、歧义变量名、无效 f-string、未用变量），修完不改变任何行为。若引入 `I/UP/B/S`，同一次运行报 **2385 项**（含 import 排序、语法现代化、bugbear、bandit），绝大多数是风格问题，会顺带重排并改写大量既有文件——与项目规则 §5「不进行无关重构」直接冲突；更现实的问题是，一个上千行、纯风格改动的 diff 会让 code review 彻底失效：reviewer 再也看不出哪一行是真正的逻辑变更。
  2. **规则集必须像版本一样钉死**。实测证据：同一份代码，不写 `select` 报 219 项，写成本集报 36 项——因为 ruff 某版本起把默认集显著放宽了。不写死的话，「这次提交能不能过 lint」就取决于 CI 当天装到哪个版本，同一份提交会时红时绿；而「重跑一次就好了」这种现象会让人彻底不再信任这道门禁。
  3. **不启用 `ruff format`**：本仓库代码为手写、风格已基本一致。加格式门禁等于一次性重排几乎所有 `.py` 文件，产生一个巨大且纯风格的提交，其唯一效果是污染 git 历史（`git blame` 被冲散）。
  4. **迁移可逆性进 CI 的收益/成本比最高**。13 个迁移都写了 `downgrade()`，但「写了」不等于「能用」——只有真跑一遍才知道。这类腐坏平时无人察觉，只在真需要回滚时才炸，而那时已经身处事故之中。成本只是在空库上多跑两次迁移（几秒）。
  5. **让 service 适配测试，而不是改 40 个测试文件**：改测试属于「无关改动」，且会削弱「CI 跑的就是本地跑的那套断言」这条性质——同一个常量出现两套值之后，出问题时第一件要怀疑的事会变成「是不是端口配错了」。
  6. **不推送镜像**：推送需要 `packages:write` 权限与 registry 凭据。一个纯粹回答「能不能构建」的步骤不该带上这把钥匙；仓库也没有镜像发布需求（若将来有，那应该是一个独立的发布 workflow，带环境审批）。
  7. **断言「CI 的环境变量恰好是那三个默认值不可用的项」**（而不只是「包含」）：CI 与本地应当**只差「谁提供 Postgres / Redis」**。多设一个键（例如顺手加 `APP_ENV=production`）就引入了第三种配置，会让「CI 绿 ⇒ 本地绿」这条性质悄悄失效。
- 配套实现细节：
  - **环境变量名做交叉校验**：CI 传的每个键都要能在 `Settings.model_fields` 里找到（拼错如 `DATABSE_URL` 不会报错，只会静默按默认值运行，于是 CI 去连 `postgres:5432`，失败信息看起来却像「service 没起来」）——与 `test_prod_compose.py` 对 compose 的做法一致。
  - **service 的 `--health-cmd` 必须配**：没有健康检查时，容器一起来 workflow 就继续跑，安装依赖的几十秒**通常**够 Postgres 就绪——于是这变成一个「多数时候能过」的偶发失败。
  - **迁移三步写在同一条 shell 里 + `set -euo pipefail`**：拆成三个 step 时若失败被吞，后续步骤会在旧库上继续，最终呈现出「pytest 通过」的假绿。
  - **CI 的 Python 版本从 Dockerfile 反向读出并比对**（`FROM python:3.13-slim` ↔ `PYTHON_VERSION: "3.13"`）：两处漂移的后果很隐蔽——CI 全绿，而生产镜像里是另一个 Python 大版本，差异只在部署后暴露。
  - **lint 工具与运行时依赖分文件**（`requirements-dev.txt` 以 `-r requirements.txt` 扩展）：`requirements.txt` 被 Dockerfile 用于生产镜像，把 ruff 装进去既是死重量，也让「生产镜像里装了什么」无法单独审计。
  - **最小权限 + 禁用 `pull_request_target` + 每个 job 设 `timeout-minutes`**：后者的默认上限是 360 分钟，一个卡住的 job（例如等一个永远不就绪的 service）会白占六小时。
- Trade-off：①**CI 不做容器全栈验证**（不在 runner 上起 `docker-compose.prod.yml` 跑 nginx 反代）——那需要额外拉取镜像与数分钟等待，且属部署验证；代价是「反代层被改坏」不会被 CI 拦住，只能由 `tests/test_nginx_config.py` 的离线契约测试兜住（它覆盖了可静态检查的全部性质，包括 XFF 覆盖语义与信任网段交叉校验）。②规则集固定意味着 ruff 新版本里的新规则不会自动生效，升级需要人工评审——这是**有意**的：门禁的变化应当是显式的，而不是某天突然多出几百项。③`REQUIRED_SERVICE_PORTS` 这份清单依赖「测试仍然硬编码这些端口」；若将来测试改成从配置读地址，清单会过期——已加反向断言（清单里的每个端口必须在 `tests/` 中确有引用），过期时测试会红。


