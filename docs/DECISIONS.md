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
