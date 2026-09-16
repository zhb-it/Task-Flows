# Testing Strategy

## 技术
pytest、pytest-asyncio、httpx。

## 测试层次
- 核心 Service 单元/业务测试
- API 集成测试
- 数据库测试
- Redis 限流测试
- Celery 任务测试

## 优先级
1. 认证与授权
2. 状态机
3. 事务与数据一致性
4. 资源级权限/IDOR
5. 限流
6. 异常与边界

## 测试环境
独立测试数据库，不污染开发数据库。使用 fixture 管理 db_session、client、test_user、test_team、test_project、test_task。

## 团队与项目权限矩阵（TASK-030）
`tests/test_team_project_permissions.py` 系统性验收「全局 RBAC 角色 × 团队角色 × 操作」三层判定（ TASK-027/028/029 决策的汇总回归）：

- 阵容：owner（admin 全局 + 团队 OWNER）、tmember（admin + 团队 MEMBER）、tadmin（admin + 团队 ADMIN）、gmember（member + 团队 MEMBER）、outsider（admin 非成员）、nobody（无角色）。
- **§56 Phase 4 验收**：ADMIN / MEMBER 权限表现不同——member 全局角色（读 5 + 基础写 5，无 team:/project: 写权限）对团队/项目只能读（写操作 403 `Permission denied: {perm}`）。
- 双层判定两个方向：团队角色再高（gmember 升团队 ADMIN）补不了全局权限缺失（仍 403 team:invite）；全局权限再高（tmember 全局 admin）也过不了资源级归属（团队改删 404、项目改删 403、邀请 403）。
- IDOR 契约：outsider 对 team/project 读/改/删全部 404 且与「不存在」同文案；列表不泄露（返回空）。
- 可见性翻转：邀请入队后 GET 团队/项目即刻 200。

## 状态机与审计（TASK-040）
`tests/test_state_machine_audit_flow.py` 整合 §35「Task 重点测试」与 §56 Phase 8「状态机」验收条款，并落实 TESTING 优先级 #2（状态机）/ #3（事务与数据一致性）：

- **§56 Phase 8 完整链路演示**：一次跑通 `TODO → IN_PROGRESS → REVIEW → DONE`，并演示 `DONE → TODO` 被拒绝（规格原文两条）。
- **§35 Task** 状态正常流转（每跳 200 且持久化）/ 非法状态流转（跨级、同状态、终态出边全 409 且状态不动）/ DONE 不允许回退——验收面整合。
- **审计 ⇄ 状态一致性**：每次成功流转恰好一条 `action=task:transition` 日志，日志序列的 `old_status`/`new_status` 与任务状态链严格衔接；被拒流转不产生日志。
- **§55.3 事务原子性**：状态变更与写 OperationLog **同事务提交**——monkeypatch 让写日志失败时，任务状态一并回滚（仍 TODO）且库中零日志，证明不存在「状态变了但没日志」的不一致。

底层规则与端点的细粒度覆盖分别在 `tests/test_state_machine.py`（TASK-037 离线规则 29 项）、`tests/test_task_transition_api.py`（TASK-038 端点 7 项）、`tests/test_operation_log_api.py`（TASK-039 日志查询 6 项）。

## 附件上传/下载安全（TASK-042）
`tests/test_attachment_api.py` 27 项 HTTP 端到端，覆盖 TESTING 优先级 #1（认证与授权）、#3（事务与数据一致性）、#4（资源级权限/IDOR）、#6（异常与边界），并把开发文档 §9 安全清单中的「文件上传漏洞 / 路径穿越 / 存储型 XSS / 响应头注入」逐条转成可执行断言：

- **存储隔离**：`storage_root` 夹具把存储后端指向 `tmp_path`，并覆盖 `app.services.storage._backend` 单例——这是全项目唯一注入点，因此不必 monkeypatch 每个调用方；断言真实落盘位置在临时目录内，不污染仓库 `storage/`。
- **大小限制**：真实超限字节流（4KB > 1KB 上限）→ 413，且**零残留**（无元数据、无半成品文件）；边界用例「恰好等于上限」必须通过（防误伤）。校验走「边写边累计」，不依赖伪造 `Content-Length`。
- **MIME 白名单**：`.exe` / `.sh` / `.html` / `.php` / 无扩展名 → 415；`.PNG` 大写通过；**客户端自报 Content-Type 被忽略**（`report.pdf` 报 `text/html` 仍入库 `application/pdf`）。
- **文件名清洗与路径穿越**：`../../../../etc/passwd.txt` → `passwd.txt`，且 `storage_path` 中不含 `passwd`/`..`（证明 key 完全由服务端生成）；`..\..\Windows\win.ini.txt` → `win.ini.txt`；含 `\r\n` 的文件名被剥离（防响应头注入）；`CON.txt` → `_CON.txt`。
- **文件系统一致性**：空文件 → 400 且即时回收；元数据在但物理文件被外部删除 → 404（而非 500）；超限失败后目录内无文件残留。
- **唯一性与覆盖**：同名文件重复上传两次，两条 `storage_path` 不同且两次下载内容各自独立。
- **授权**：功能级 403（无角色用户对上传/列表/下载/删除四端点，`Permission denied: {perm}`）；资源级 404 四端点同文案（局外人、不存在的 id，`Task not found` / `Attachment not found`）；**成员可正常上传/下载，且可删除自己的附件**（`attachment:upload` 复用），团队成员删他人附件 403，团队 ADMIN 删他人 200。
- **响应头**：`Content-Disposition` 为 RFC 5987 百分号编码形式且整体可 `.encode("ascii")`（非 ASCII 文件名 `报告.pdf` 亦安全）；`X-Content-Type-Options: nosniff` 存在；`Content-Length` 与入库 size 一致；下载字节与上传字节逐字节相同（含 `\x00\xff`）。
- **审计与级联**：删除写 `action=attachment:delete` 且 payload 精确匹配；删除后元数据与物理文件**同时**消失；删任务 / 删用户级联清附件元数据。

零残留策略同前：审计日志 → 附件 → 任务 → 项目 → 团队 → 用户（RESTRICT 全链精确拆除）。

## 附件对抗性安全（TASK-043）
`tests/test_attachment_security.py` 19 项，从**攻击者视角**补齐 TASK-042 未覆盖的盲区，并固化 TASK-043 修复的真实缺陷（均由探测发现，非推测）：

**TASK-043 修复的缺陷**
1. **非法 `storage_path` 触发 500**：key 被绕过 API 改写为穿越片段/绝对路径时，存储层抛 `UnsafeStorageKeyError`，而 042 只捕获了 `StorageObjectNotFoundError` → 未捕获异常变成 500 + 堆栈，泄露存储根的校验规则。修复：下载路径一并映射 404（含响应体不含内部文案的断言）；删除路径跳过物理删除直接删记录，避免形成**永远删不掉的脏记录**。
2. **`%XX` 百分号编码绕过**：`a.txt%00.png` 被判为 `png`，但 `%00` 在下游被 URL 解码后成 NUL 并截断字符串，使「校验的扩展名」与「实际使用的扩展名」分叉。修复：清洗阶段主动剥离 `%XX`，并断言入库名不含 `%`、无 NUL、有效扩展名与展示名一致。
3. **无主名文件名行为不一致**：`.txt` 经清洗成 `txt` 后以「扩展名不在白名单」为由被拒，原因与表象不符。修复：无主名显式判定，统一 415；纯分隔符/空白/点仍 400。

**固化的契约（防回归）**
- 多段扩展名只看**最后一段**；磁盘 key 的扩展名取自白名单解析结果（`shell.php.txt` → 磁盘 `.txt`，`release.tar.gz` 正常通过）。若有人改成「检查所有扩展名」会误拒正常文件名，此测试会拦住。
- 客户端 `Content-Type` 无论如何伪造（`text/html`、`application/x-php`、`image/svg+xml`、空串）都不影响入库类型。
- 「有权限但非成员」→ 404 且响应体不泄露文件内容；「无 Token」→ **401**（与 404 可区分，前端据此判断引导登录还是提示无权限）。

**其他对抗面**
- 存储根之外零写出（7 种编码/分隔符组合）；存储根直接子项仅 `tasks/`。
- 响应头注入：引号/CRLF/分号/`\x00` 文件名入库被清洗，响应头无额外字段且整体为 ASCII。
- 下载的 `Content-Length`、DB `size`、实际字节数三者恒等（多种长度）。
- 畸形 multipart（无 body / 字段名错 / 缺 boundary / 纯 JSON）不产生 500，且不留记录。
- 并发同名上传：8 个并发请求各自生成独立 `storage_path`，内容一一对应（无 TOCTOU 覆盖）。
- 审计日志只含 `{task_id, attachment_id, filename}`，不含 `storage_path`（§48 敏感日志泄露）。
- 大小限制边界扫描：`limit-1`/`limit` 通过、`limit+1`/`3×limit` 拒绝，磁盘仅留 2 个文件（被拒的不留痕）。

零残留策略同前：审计日志 → 附件 → 任务 → 项目 → 团队 → 用户。

## 评论与附件整合验收（TASK-044）
`tests/test_comment_attachment_flow.py` 16 项 —— Phase 7 收官（纯测试任务，同 TASK-040 先例：无应用代码/迁移变更）。**不重复** TASK-041/042/043 的细粒度断言，只补三个分散模块**放在一起才暴露**的跨模块问题：

- **共存**：同一任务上评论与附件交错写入，两条时间线互不污染；跨任务零串联（§16「评论必须属于任务」+ §17 同理）；磁盘上正好 N 个文件且都在该任务的目录下。
- **审计命名空间不串号**：评论删除与附件删除写**同一张 `operation_logs`**，`action`/`resource_type`/`payload` 各归其位（comment 的 id 与 attachment 的 id 可能重号，靠 `(resource_type, resource_id)` 索引分开）。同时固化契约：**创建评论与上传附件都不写审计日志**（§16 规则 4 只要求删除写日志；防止后续「顺手加审计」改变 §15 语义边界）。
- **§48 越权表现逐字节一致**：局外人对评论与附件的越权响应必须完全一致——8 个端点全部 404，「不存在」与「存在但无权」同文案，且响应体不含资源标识/内容/`storage`/`traceback`。前端要能用统一逻辑区分 403 与 404，任何一类资源给不同文案都是设计缺陷。
- **认证 ≠ 授权**：无 Token 时 **7 个端点全部 401**（不是 404/403）；**功能级 403 先于资源级 404**——无全局权限者对**真实存在的**和**不存在的** id 都得到 403，因此无法用状态码差异枚举 id。
- **删除权限层级在同一阵容下各自成立**（最易被重构抹平的一条）：评论=作者本人或团队 OWNER/ADMIN；附件=上传者本人或团队 OWNER/ADMIN。用同一组用户（owner / 团队 ADMIN / 团队 MEMBER，全局均 admin）同时验证两条规则：普通成员删他人内容两资源都 403 **且文案各自准确**；普通成员删自己内容两资源都 200；团队 ADMIN 与 OWNER 删他人内容两资源都 200。互补边界：**member 全局角色**（无 `comment:delete`）删自己的评论仍被功能级 403 先挡（`Permission denied: comment:delete`）。
- **级联**：删任务 → 评论与附件元数据**同时**级联清；删用户 → 其评论与附件随 FK CASCADE 消失，但**审计日志保留**（`operation_logs.user_id` 无外键，TASK-039 决策）——三条规则合起来才是完整的数据生命周期契约。
- **§55.2 事务原子性**（TESTING 优先级 #3）：monkeypatch 让 `write_operation_log` 抛错，评论/附件删除均**整体回滚**（记录仍在、零日志）。附件路径额外固化「先删文件再删记录」的已知取舍：审计写失败回滚后**物理文件已不在**——文件不可回收优于「记录删了文件还在」。
- **分页契约一致**：两类列表的 skip/limit 语义相同，`limit=0`/`limit=101`/`skip=-1` 均 422。
- **生命周期独立**：删评论不影响附件（记录与文件都在）；删附件后磁盘与 DB 同步清零，无孤儿文件。

**测试有效性验证（变异测试）**：临时移除评论删除的资源级授权判定后，`test_delete_authorization_differs_per_resource_same_roster` 立即失败（得到 200 而非 403），证明该断言真实承重、非空过；随后已还原源码（blob hash 与 HEAD 逐字符一致）。

零残留策略同前：审计日志 → 附件 → 评论 → 任务 → 项目 → 团队 → 用户。

## Redis 连接与 Key 约定（TASK-045）
`tests/test_redis.py` 24 项，Phase 8 首个任务。**不实现限流**（那是 TASK-046），只交付连接层与 Key 约定这两项「后续所有 Redis 代码都要踩在上面」的地基。测试分三类：

**1. Key 命名约定（纯函数，离线，13 项）**
`app/core/redis_keys.py` 是**唯一**的 Key 构造点，必须 100% 覆盖：
- 形状：`build_key("ratelimit","ip","1.2.3.4")` → `taskflow:ratelimit:ip:1.2.3.4`；`rate_limit_key` / `jwt_blacklist_key` 各自格式。
- **前缀稳定性显式钉住**：`KEY_PREFIX == "taskflow"`。前缀是数据兼容性契约（改它等于迁移线上所有键），因此断言字面量而非引用常量——否则「常量改了、断言跟着改」的循环会让测试失去意义。
- 非字符串 part 自动 `str()` 转换（user id 是 `int`，调用方不该被迫手写 `str()`）。
- **非法输入拒绝而非静默拼接**：空 purpose → `ValueError`；purpose 含 `:` → `ValueError`（会破坏「用途段」结构）；空 jti → `ValueError`。
- **scope 隔离**：同一标识在 `ip` 与 `user` 两个 scope 下必须是不同键，否则两类流量会互相挤兑配额。
- 全部 Key 以 `KEY_PREFIX + ":"` 开头——运维 `SCAN taskflow:*` 的安全前提。

**2. 连接层契约（离线，5 项）**
- **import 阶段不建立连接**：这是关键契约——否则没有 Redis 的环境连应用都 import 不了。单进程内断言 `_client is None` 不可靠（别的用例可能已建好单例），因此**起一个全新子进程**、把 `REDIS_URL` 指向**不可达**的 `127.0.0.1:6399` 再 `import app.main`：若 import 期真的去连接，这里会挂住或报错。通过即证明「懒连接」成立。
- **连接池单例**：同一进程内两次 `get_redis_client()` 返回同一实例。每次请求新建 client（哪怕同 URL）都会新建连接池，是典型资源泄漏。
- **`decode_responses=True`**：限流与黑名单逻辑里到处是字符串比较，若每个调用点各自 `decode` 会引入不一致。通过 `connection_pool.connection_kwargs` 断言。
- **依赖注入语义**：`Depends(get_redis)` yield 的是**共享**客户端，请求结束**不关闭**它（与 `get_db` 的每请求一份、必须关闭形成对比——Redis 客户端是无状态连接池句柄，应跨请求复用）。
- **`reset_redis` 只清引用不关连接池**：清后 `_client is None`，再取会重建，且新旧 `connection_pool` 不是同一个。

**3. 真实 Redis 连通性（6 项，连不上则 `skip`）**
连接层的问题（URL 解析、`decode_responses` 实际行为、池生命周期）在假客户端上照不出来，而这恰是本 TASK 的交付物，因此连宿主 Redis 7（宿主 **6389**／容器 6379，与 PostgreSQL 5433/5432 的映射惯例一致）：
- `PING` 通；`SET`/`GET` 拿到 **`str`** 而非 `bytes`。
- **Key 构造器产出的键能被真实 Redis 接受**，且 `scan_iter(match="taskflow:test:<token>*")` 能命中——运维清理依赖前缀可扫描。
- `TTL` 语义可用（限流与黑名单都依赖）。
- **ZSET 基础设施自检**：`ZADD`/`ZCARD`/`ZREMRANGEBYSCORE`/`ZRANGE`/`ZCOUNT` 全部可用。本 TASK 不实现限流，但要确保 §22 所需的**数据结构在连接层就绪**，否则 TASK-046 会卡在环境问题上。
- `pipeline(transaction=True)` 可用。

零污染策略：所有键以**本次运行唯一 token** 为中间段（`taskflow:test:<token>:*`），`try/finally` 逐键 `DELETE`；不 `FLUSHDB`（会误删他人数据）。

## 滑动窗口限流（TASK-046）
`tests/test_rate_limit.py` 22 项，Phase 8 第 2 个任务。**全部连真实 Redis**（宿主 6389），不可达则 `skip`——理由见 DECISIONS 016：限流被击穿的三个常见根因（判断/写入竞态、member 不唯一导致 ZSET 折叠、TTL 缺失导致无界增长）在假客户端上一个都测不出来，而那正是本 TASK 的交付物。

**1. Lua 脚本语义（9 项）**
- **额度精确**：窗口内恰好放行 `limit` 次，第 `limit+1` 次起拒绝；`current` 在额度内递增、超限后停在 `limit`（不因被拒而虚增）。
- **被拒不写入 ZSET**：连续 10 次被拒后 `ZCARD` 仍等于额度。若写入了，持续攻击会让 ZSET 无界增长，且窗口永远滚不过去（每分钟都有新成员）——等于把自己永久锁死。
- **TTL 有界**：`SET` 后 `0 < PTTL <= 窗口毫秒数`（§22 第 5 步）。
- **滑动恢复**：1 秒窗口 + 限 2 次，睡 1.1 秒后额度恢复，且旧成员已被 `ZREMRANGEBYSCORE` 清掉（`ZCARD == 1`）。
- **`Retry-After` 由最早成员推算**：额度 1、窗口 30 秒，被拒时 `0 < retry_after <= 30`。
- **member 唯一性是隐式契约**（显式钉住）：同一 member 发 3 次 → `ZCARD == 1`（折叠）；唯一 member → `ZCARD == 3`。防止将来有人图省事用固定字符串（如 IP）作 member 而被击穿。
- **并发原子性**（§22 明确要求，核心用例）：20 个并发请求 gather，放行数**恰好**等于额度 5，`ZCARD == 5`。这是必须用 Lua 的直接证据——若「读计数 → 判断 → 写入」拆成多条命令，并发下会全部放行。
- 非法参数（`limit=0` / `window_seconds=0`）→ `ValueError`。
- `enforce_rate_limit` 仅在拒绝时抛 429，放行时无操作。

**2. 中间件契约（9 项）**
- `/health` **不限流**（连续 5 次 200）——否则编排器探针会消耗额度甚至被拒；`/api/v1` 受限。
- **429 响应体用项目统一信封**：`set(body.keys()) == {"detail"}`、含「Rate limit exceeded」、带 `Retry-After >= 1`（§26）。
- 放行响应带 `X-RateLimit-Limit` / `X-RateLimit-Remaining` 配额头。
- **已认证按 user 维度**：同一 user 第二次请求即 429，且 `taskflow:ratelimit:user:<id>` 键确实存在；同一 IP 的匿名请求不受该 user 消耗影响。
- **非法 Token 退化为 IP 维度**：首个请求仍得 401（限流不改变认证语义），第二个按 IP 上 429。
- `rate_limit_enabled=False` 完全不限流。
- **Redis 故障 fail-open**：monkeypatch 让 `check_rate_limit` 抛 `ConnectionError`，5 次请求仍到达业务层（401），无一返回 429——限流不应成为新的单点故障。
- **IP 与 user 两层配额互不消耗**（隔离性）。

**3. 配额配置（1 项，离线）**：`rate_limit_requests` / `rate_limit_window_seconds` / `rate_limit_enabled` 有可用默认值且类型正确。

**3. 配额配置与延迟上界（4 项，离线）**
- 配额配置有可用默认值且类型正确（见 DECISIONS 015）。
- **Redis 客户端必须设置 `socket_timeout` / `socket_connect_timeout`**（DECISIONS 019）。
- 中间件必须声明单次调用的延迟上界（`RATE_LIMIT_CALL_TIMEOUT_SECONDS` 在 `(0, 5]`）。
- **连真实不可达地址**（`127.0.0.1:1`）验证「fail-open + 延迟有上界」：请求仍到达业务层（401）且单请求耗时 <5s。

**测试套件级配置（`tests/conftest.py`）**
限流中间件对每个 `/api/v1` 请求生效后，全量回归出现 2 个失败——`test_refresh.py` 的两个用例断言 401 却得到 **429**。根因：所有测试文件共用同一来源地址（`ASGITransport` 默认 `127.0.0.1`），因此共享同一个 IP 维度限流键，而单文件的请求数就超过 60 次/分钟。这是**测试间的隐式耦合**（结果取决于此前跑过多少测试），不是实现缺陷。修法：`conftest.py` 用 autouse fixture **默认关闭限流**，`test_rate_limit.py` 在用例内显式开启并调小额度。详见 DECISIONS 021。

**测试隔离的关键手法**：中间件按 `request.client.host` 取 IP 维度标识，而 `ASGITransport` 默认所有用例都是 `127.0.0.1` —— 前一个用例消耗的额度会泄漏到后一个，产生「莫名先到 429」的假失败（本文件首轮开发时确实踩到：`X-RateLimit-Remaining` 得到 7 而非 9）。因此限流用例经 `ASGITransport(client=("10.99.x.y", 0))` 分配**独占 IP**，用完删除该 IP 的键。认证类用例还需把 `get_db` 覆盖到**宿主 5433 的真实开发库**：`.env` 的 `localhost:5432` 是另一台 PostgreSQL，不覆盖会在连接阶段抛错、掩盖真正的中间件行为。

**测试有效性验证（变异测试）**：把 Lua 中的 `if current >= max_requests then` 改为 `if false and current >= max_requests then`（永不超限）后，**10 个用例立即失败**（含 `test_allows_up_to_limit_then_rejects`、`test_rejected_requests_are_not_recorded`、`test_concurrent_requests_do_not_breach_limit`、`test_api_is_rate_limited`、`test_429_body_and_headers_follow_project_contract`），证明断言真实承重、非空过；随后已还原源码并核验。

**峰值发现（TASK-046 附带修复的环境缺陷，见 DECISIONS 019）**：接入限流后全量测试从约 5 分钟劣化到 15 分钟以上并看似卡死，单个用例从 <1s 涨到 **27s**。三层根因：①`.env` 的 `REDIS_URL=redis://localhost:6379/0` 指向的**不是本项目 Redis**（compose 把项目 Redis 发布在宿主 **6389**，而 6379 上另一个 Redis 需要 AUTH）；②客户端不带密码 → NOAUTH → 按默认重试直到宽松的默认超时（实测单次 PING 失败 **5.02s**）；③限流对每个请求都访问 Redis，把该成本乘到全站。另有 Windows 陷阱：`localhost` 优先解析到 IPv6 `::1`，而 Docker 只发布 IPv4。修复：客户端显式设置 socket 超时（1.0s）、中间件加 `asyncio.timeout` 兜底（2.0s）、`.env` 改用 `127.0.0.1` + 正确端口（5433 / 6389）。修复后限流单次调用实测 **0.6ms**，全量回归回到 5m49s。

**阈值说明**：§22 未定义数值，采用 `60 次 / 60 秒`（可经 `.env` 的 `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_ENABLED` 覆盖），见 DECISIONS 015。

## 限流整合验收（TASK-047）
`tests/test_rate_limit_integration.py` **15 项**，Phase 8 收官测试任务（纯测试，未改应用代码，同 TASK-040/044 先例）。

**定位**：**不重复** TASK-046 的 22 项细粒度断言（Lua 语义、维度判定、429 信封、fail-open、延迟上界），只测那些**必须借助真实用户 + 真实业务端点 + 真实审计表 + 真实 Redis 键空间**才能观察到的跨模块性质。

**方法论（同 TASK-043/044）**：先跑一次性探测脚本，观测 10 个交叉面（跨端点配额、多用户隔离、换 IP、写副作用、审计、暴力破解、键命名空间与 TTL、匿名洪水、404 路径、响应体泄露），**据观测结果**再决定写什么断言；脚本用完即删。本轮探测确认十个面全部行为正确（**未发现缺陷**），因此本文件的价值是**契约固化**——让「按端点限流」「限流写审计」「去掉 TTL」「member 用固定串」这类改动立刻失败。

**1. 限流 × 认证（TESTING 优先级 #1）**
- **登录暴力破解被挡**：连续失败登录 → `401,401,401,429,429`。§22 未给登录单独配额，但中间件覆盖全部 `/api/v1`，因此**登录天然受保护**——这是防暴力破解的第一道闸门（密码哈希是第二道）。
- **限流不泄露账号是否存在**：存在的用户 + 错密码 与 不存在的用户，在超限前后**文案都一致**（未超限都是 401 同文案，超限都是 429 同文案）——攻击者无法用 401/429 差异枚举账号。
- **匿名洪水被挡在认证之前**：无 Token 的 DELETE 洪水 → `401×3 → 429×2`。限流是中间件、认证是路由依赖，因此 429 必然先于 401——**这正是想要的**，否则不带 Token 就能无限打认证端点。
- **换 IP 绕不过 user 维度**：同一用户每次请求换一个独占 IP，第 4 次仍 429。若退化成按 IP 计数，一组代理就能把额度放大 N 倍（§22 User 维度的安全价值所在）。

**2. 限流 × 业务副作用（优先级 #3）**
- **被限流的写请求零落库**：`POST /tasks` 连打 5 次 → `201×3 + 429×2`，库中任务数**恰好 3**。TASK-046 只断言了状态码；这里断言**副作用**，防止将来把判定挪到 `call_next` 之后（「先执行再计数」）。
- **被限流的请求不写审计日志**：一次成功流转产生 1 条 `task:transition`，此后的 429 产生 0 条。审计记录**发生过的业务动作**（§15），被限流的请求根本没到业务层；否则一次洪水就会灌满审计表、淹没真正的线索（DECISIONS 023）。
- **额度跨端点共享**：同一用户在 `/api/v1/users/me` 与 `/api/v1/teams` 间切换，额度不因换端点而重置（§22 一个身份一个 ZSET，无端点维度；DECISIONS 022）。
- **两个用户额度独立**：alice 耗尽后 bob 仍从满额开始——同一 NAT 后不互相挤兑。
- **并发 × 隔离叠加**：20 个并发请求分属两个用户，各自**恰好**放行 3 次。若限流被击穿（判定/写入竞态）或维度串了（都落到同一把键），放行数都不会是 `(3, 3)`。

**3. 限流 × 运维（TASK-045 的 Key 约定在第 046 上的交叉）**
- **键只在自己的命名空间且都有 TTL**：用「跑之前/之后 `SCAN taskflow:*` 取差集」的方式，断言本次用例新增的键全部以 `taskflow:ratelimit:` 开头、且 `TTL > 0`。取差集而非全量扫描，是为了不受其它测试遗留键影响，也**不 FLUSHDB**。命名空间保证不与将来的 `jwt` / `celery` 用途互相覆盖，TTL 保证被攻击产生的键不会永久占内存（§22 第 5 步）。
- **不存在的路径也吃配额**：`404×3 → 429×2`。中间件按前缀而非已注册路由判定，否则可以用随机路径无限枚举。

**4. 限流 × 错误契约（§26 / §48）**
- **429 不泄露内部标识**：响应体不含 user id、来源 IP、`taskflow` 前缀、`Traceback`（§48）。
- **429 与 401/403/404 同信封**：四类客户端错误**全部**是 `{"detail": ...}`，前端可用统一逻辑处理。
- **放行的请求业务结果 + 配额头同时正确**：201 创建成功且 `X-RateLimit-Limit` / `X-RateLimit-Remaining` 齐全——中间件改写响应不会破坏业务。
- **关掉限流立刻恢复**：`rate_limit_enabled=False` 后，已被限死的身份马上 200。这是误伤时的**不改代码、不重启**的逃生舱，断言保证它真的作用于判定路径而非摆设。

**测试有效性验证（变异测试，4 个变异全部被杀死）**
1. 去掉 429 分支（永不拒绝）→ **13 failed**；
2. 身份维度退化为只用 IP → **3 failed**（恰好是三项 user 隔离用例，说明断言精准）；
3. Lua 去掉 `PEXPIRE` → **1 failed**（键 TTL 用例）；
4. `member` 改用固定字符串（ZSET 折叠）→ **10 failed**（含并发用例）。

还原后源码 blob hash 与 HEAD 逐字符一致（`git status` 干净）。

零残留策略同前：审计日志 → 任务 → 项目 → 团队 → 用户；Redis 键只删本次新增（差集），不 `FLUSHDB`。

## Celery App / Worker（TASK-048）

`tests/test_celery_app.py`，11 项，全部不依赖真实 Redis（Broker → Worker → Backend 真实链路由 compose 部署冒烟负责，见下）：

- **Broker/Backend 派生规则（2 项）**：默认回落 `REDIS_URL`（DECISIONS 026）；显式 `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` 可覆盖。
- **序列化安全（1 项）**：`accept_content` 恰为 `{json}`，禁 pickle（DECISIONS 027）。
- **可靠性参数（4 项）**：`task_acks_late` / `task_reject_on_worker_lost` / `worker_prefetch_multiplier=1`（at-least-once 投递三件套，规则 §8 落点）；`task_track_started`；软/硬超时从配置接线且硬 > 软；默认值合理。
- **键约定（1 项）**：broker 与 backend 的 `global_keyprefix` 均为 `taskflow:`（TASK-045 约定）。
- **任务执行（2 项）**：`app.ping` 已注册；eager 模式执行返回 `pong`。
- **import 安全（1 项）**：子进程在 `REDIS_URL` 指向不可达地址时导入 `app.tasks.celery_app` 必须即时成功——Celery 连接是惰性的，防止有人在模块顶层加预连接。

**配置缓存纪律**：`get_settings` 是 `lru_cache` 的，凡覆盖环境变量的用例前后都要 `cache_clear`（本文件用 `_fresh_settings_cache` autouse fixture 局部处理）。

**compose 部署冒烟（真实链路）**：
1. `docker compose up -d --build` 四服务全部 Up（worker 带 `celery inspect ping` 健康检查）；
2. `celery inspect ping` → `1 node online`；
3. app 容器内 `ping.delay().get()` → `pong, SUCCESS`（完整经过 Redis Broker → Worker → Redis Backend）；
4. `redis-cli --scan` 实测全部 Celery 键都在 `taskflow:` 前缀之下。

## 通知异步任务（TASK-049）

`tests/test_notification_task.py`，15 项。**全部为同步用例**——任务体内部用 `asyncio.run`（Celery 同步上下文），async 用例的事件循环里嵌套 `asyncio.run` 会直接 RuntimeError；库内验证用 asyncpg 直连开发库，与任务自身的写入路径相互独立。

- **注册与接线（2 项）**：`app.create_notification` 已注册；`TASK_MODULES` 已登记 `app.tasks.notification_tasks`。
- **执行链路（3 项）**：直接调用落库（字段/`is_read=False`/`created_at`）；`content=None` 落 NULL；eager 派发经 Celery 任务机端到端。
- **§24 要求 3 不大量重复（4 项）**：同一 idempotency_key 第二次调用 → `skipped` 且仅一条；不同 key 各建一条（去重不误伤）；完成标记 `taskflow:notify_done:<key>` 带 TTL（≤7 天）；Redis 故障 fail-open 仍创建通知。
- **参数防御（2 项）**：user_id≤0 / type 空·超长 / title 空白·超长 → `ValueError` 零副作用；缺省幂等键自动生成。
- **§24 要求 2 可重试（2 项）**：`autoretry_for=(SQLAlchemyError, OSError)`、`max_retries=5`、指数退避 + 抖动、`ValueError` 不重试；幂等键唯一性。
- **FK 级联（1 项）**：删除用户 → 其通知随之清理。
- **连接层（1 项）**：`get_sync_redis_client` 沿用 socket 超时纪律（TASK-046 教训）。

**compose 部署冒烟（真实链路）**：重建镜像后 `celery inspect registered` 列出 `app.create_notification`；app 容器内真实派发（含调用方幂等键）→ Worker 落库 `{'status': 'created', 'notification_id': 32}`，字段全对、完成标记 TTL≈7 天；随后精确删除该通知与标记，表归零。

## 维护异步任务（TASK-050）

`tests/test_maintenance_tasks.py`，13 项。两个 Celery 任务（归档操作日志 `app.archive_operation_logs`、清理孤儿附件 `app.cleanup_expired_attachments`），**全部同步用例**——同 TASK-049 约束（任务体 `asyncio.run`，库内验证用 asyncpg 直连 5433，与任务写入路径独立）。

- **注册与接线（3 项）**：两任务已注册到 `celery_app.tasks`；`TASK_MODULES` 已登记 `app.tasks.maintenance_tasks`。
- **归档执行链路（4 项）**：超期日志迁入 `operation_logs_archive`、主表对应行删除、字段逐字段一致（含 JSONB `payload` 与原 `created_at` 保留）、新日志留主表；**幂等**（重投 → `archived=0`、归档表无重复，靠 id 复用 + `ON CONFLICT DO NOTHING` + 同事务删主表）；**分批**（batch_size=2 循环搬完 5 条）；参数防御（`retention_days` / `batch_size` ≤0 → `ValueError` 零副作用）。
- **清理执行链路（4 项）**：真实 `existing` 查询下孤儿物理文件被删；DB 有记录的文件保留（monkeypatch 集合模拟）；**年龄窗口**（刚写入的孤儿因 mtime 太新被跳过，改旧后删除）；参数防御（`min_age_seconds`<0 → `ValueError`）。
- **重试语义声明（2 项）**：两任务 `autoretry_for=(SQLAlchemyError, OSError)`、`max_retries=5`、指数退避 + 抖动、`ValueError` 不重试（规则 §8）。

**隔离纪律**：归档测试行用 `action` 前缀 `mt_<RUN_TOKEN>_` 隔离、teardown 精确清理两表；清理任务经 monkeypatch `settings.upload_dir` 指向 `tmp_path`，不污染真实 `storage/` 卷。

## Celery 任务韧性（TASK-051）

`tests/test_task_resilience.py`，8 项。**纯测试任务，不改应用代码**——只把 TASK-049/050 已覆盖的「声明层」推到「行为层」，类比 TASK-040/044/047 的整合验收定位。任务体内部 `asyncio.run`，故全部同步用例；验证用 asyncpg 直连 5433 与任务写入路径独立；幂等键 / 日志行 / 用户带本运行唯一前缀（`rsl_<RUN_TOKEN>_`），teardown 精确清理，开发库零残留。

- **重试行为（真实，2 项）**：瞬态 `SQLAlchemyError` 后 Celery 经 eager `delay()` 真的重跑并最终成功、**恰好 1 行**（幂等去重与重试协同）；永久故障超 `max_retries` 后真抛错、`_insert_notification` 被调用 `1+max` 次、**零通知行**（§8 failure / §24 要求 1）。
- **失败短路（1 项）**：非法参数在触达 DB 前被 `_validate` 拦截——`_insert_notification` **0 次调用**、0 重试、0 行（`ValueError` 不在 `autoretry_for`）。
- **维护任务经 Celery 任务机（2 项）**：`archive_operation_logs.delay()` / `cleanup_expired_attachments.delay()` 端到端执行（此前只测直接调用）。
- **清理重投递幂等（1 项）**：孤儿删后再跑一遍 → `deleted=0`、`errors=0`（删文件幂等 + 孤儿判定只读 DB）。
- **整体 at-least-once 安全（1 项）**：通知 / 归档 / 清理**各跑两遍**，累计副作用 = 单跑一遍，跨模块互不串扰。
- **超时不被绕过（1 项）**：三个业务任务都不覆盖 App 级 `soft/hard_time_limit`，§8 的 300/600s 对其生效（`hard_time_limit` 未显式设置时非对象属性，断言用 `getattr(..., None)`）。

**不重复既有**：未重写 `autoretry_for` 声明、幂等键跳过、Redis fail-open 等 TASK-049/050 已覆盖的细粒度断言，只补行为层与跨模块整合。

## Notification Model（TASK-052）

`tests/test_notification_model.py`，16 项。**检查项落地，不改应用代码**——DECISIONS 029 把建模提前到 TASK-049，本 TASK 把「建模完整性」固化为可回归测试（对齐 TASK-021/026/031 的 Model TASK 惯例）。建模本身（`app/models/notification.py` + 迁移 `b7d2e9a4c6f8`）已在 TASK-049 落库，本文件只验证它仍符合 §18 七字段与决策（DECISIONS 029）。

- **离线模型（10 项）**：表注册于 metadata、`__tablename__=="notifications"`、列集严格等于 §18 七字段、`id` BigInteger 主键、`user_id` FK→users CASCADE 且单列索引、`type`/`title` 非空 String(50/255)、`content` 可空 Text、`is_read` 非空默认 false、`created_at` timezone-aware 默认 now、`(user_id, created_at)` 复合索引、`__repr__` 含标识。
- **DB 集成（6 项）**：七字段 roundtrip、`content` 可空不传成功、`is_read`/`created_at` 有 DB 默认值、删用户 CASCADE 清通知、按 `user_id` 降序查主访问路径。

**隔离纪律**：写入用户 username 带 `ntf_<RUN_TOKEN>_` 前缀、autouse teardown 删前缀用户（通知随 FK CASCADE 清），开发库零残留；限流由 `conftest.py` autouse 默认关闭。

## 通知 Service/API（TASK-053）

`tests/test_notification_api.py`，**11 项**。真实产品应用（`app.main.app`）+ 真实 Token，仅 `dependency_overrides[get_db]` 指向测试库（与 `test_operation_log_api.py` 同模式）。覆盖 §18 通知系统 / §25.8 接口 / DECISIONS 035 的权限决策。

- **A. 通知 API（资源级隔离，7 项）**：`GET /notifications` 仅返回当前用户自己的通知（最小暴露面）、按 `created_at DESC` 分页（skip/limit）；`PATCH /notifications/{id}/read` 标记自己的一条为已读、已在读幂等（再标仍 200 无副作用）；非接收人 / 不存在 → 404 同文案（`Notification not found`，IDOR 防枚举）；无 Token → 401（仅需认证、无功能级权限）。
- **B. 派发点接线（§24 异步化，4 项）**：经 `notification_dispatch` 间谍验证 TaskService 在事务**提交后**调用 `_dispatch_notification`（→ `create_notification.delay`），且不真连 broker（全局 autouse `_isolate_notification_dispatch` 把关，best-effort）。任务分配 → 仅通知被分派者（`task_assigned`）、自领（target==caller）不产生通知；任务状态变更 → 通知任务全部负责人（`task_status_changed`）、排除触发者本人。

**隔离纪律**：用户（含其通知 FK CASCADE）/ 团队链资源按 `ntfapi_<RUN_TOKEN>_` 前缀精确清理；通知直连造行（绕开 API——通知只能由系统派发，无创建端点）。触发流转的用例用 **admin** 角色 actor——`task:transition` 仅 admin 持有（§6 / API_CONTRACT.md），`member` 触发流转按协议 403（沿用既有 RBAC 契约，本 TASK 未改动）；`notification_dispatch.clear()` 用于隔离「分配派发」与「状态变更派发」两阶段断言。

## 通知 read-all 标记全部已读（TASK-054）

`tests/test_notification_api.py` 增补 **3 项**（A2 组），同模块同模式。覆盖 `PATCH /notifications/read-all`（§25.8 第三端点 / DECISIONS 036 的响应体决策）：

- **只标记未读且幂等**：3 未读 + 1 已读（预置经单条端点）→ `marked == 3`（只统计真翻转的未读条数，不计已读行）；GET 复查全部 `is_read=true`；重复调用 `marked == 0`（幂等）。
- **资源级隔离**：a、b 各有通知，a 调 read-all → `marked` 只计 a 自己的条数，b 的通知保持未读（CRUD 的 WHERE 带 `user_id` 条件，SQL 层限定自己的收件箱）。
- **空收件箱**：无任何通知 → 200 `marked == 0`（「没有未读」是合法的 0，不是 404）。
- 无 Token → 401（并入既有 `test_unauthenticated_401`，三通知端点全覆盖）。

## 通知端到端测试（TASK-055）

`tests/test_notification_e2e.py`，**7 项**。TASK-053 用 `conftest` 的 autouse `_isolate_notification_dispatch` 把派发换 no-op + `notification_dispatch` 间谍夹具**只验证接线**（通知从不被真实写出）。TASK-055 是 Phase 9 收尾的**端到端整合验收**——恢复真实派发，验证「API 动作 → 真实通知入库 → 收件箱可见 → 可标记已读 / 全部已读」整条链路。

**关键实现约束**：通知任务体用 `asyncio.run` 写库，在 async 测试 event loop 调用栈里直接 `.delay()`（eager）会触发「running loop」冲突；生产里 Worker 是独立进程（独立 loop），本文件用**守护线程**等价模拟——任务在独立线程跑自己的 loop，仍执行真实入库 + Redis 幂等逻辑，且不干扰测试 loop（与 TASK-049 直接调任务体验证 §24 同思路）。任务注册 / 接线已由 TASK-049/051/053 覆盖，本文件只关心「通知真的进收件箱」。

- **动作 → 入库 → 可见（3 项）**：任务分配 → 被分派者收件箱出现 1 条 `task_assigned`（`user_id` 对、未读、title 含任务摘要）；自领不产生通知；任务状态变更 → 全部负责人收到 `task_status_changed`、排除触发者本人（触发者收件箱为空）。
- **真实写入可读 / 全部已读（2 项）**：真实通知经 `PATCH /notifications/{id}/read` 标记已读（GET 复查 `is_read=true`）；三个真实通知下 `PATCH /read-all` → `marked==3` 且收件箱全已读。
- **内容 + 资源级隔离（2 项）**：通知 `title`/`content` 由派发方按 §18 场景填充（含任务 id）；局外人收件箱为空、持有者可见自己的——通知不泄露给非接收人。

**隔离纪律**：同 TASK-053，用户（含通知 FK CASCADE）按 `ntfe2e_<RUN_TOKEN>_` 前缀精确清理。

## 结构化日志（TASK-056）

`tests/test_logging.py`，**42 项**（TASK-060 新增 1 项，见下），全离线（不依赖 DB / Redis）。分四层：

- **JSON formatter（7 项）**：§33 固定字段齐备（timestamp/level/logger/message/request_id/user_id，无值时 `null` 以保持 schema 稳定）；timestamp 为带时区 ISO 且接近当前时间；ContextVar（request_id/user_id）注入；`extra` 字段透传（访问日志的 method/path/status_code/duration 即由此进入）；单行输出且不泄漏 `LogRecord` 内部属性（msg/args/exc_info/levelno/pathname/lineno）；异常堆栈进 `exception` 字段；非 JSON 原生类型（如 `object()`）经 `default=str` 降级——**任何日志调用都不会因格式化失败而丢日志**。
- **文本 formatter（2 项）**：开发环境人读格式（含级别/logger/message）；仍追加 request_id/user_id 与 method/path/status_code。**TASK-060 新增第 3 项**：文本格式必须渲染 `client_ip` ——文本 formatter 对额外字段是**白名单**渲染，新增访问日志字段时若只加进 `extra={...}` 而漏了白名单，该字段就**只在生产 JSON 里存在**（开发环境看不到，而开发环境恰恰是人看日志的地方）；这个缺口 pytest 测不出（用例只断言 JSON 负载），是容器冒烟发现的。
- **敏感脱敏（13 项）**：§33 硬禁止项。parametrize 覆盖 password/passwd/pwd/access_token/refresh_token/token/secret 七类键名（值变 `***`、**键名保留**）；非敏感字段不受影响；嵌套 dict 逐层脱敏；message 里的 `password=hunter2` 脱敏为 `password=***` 且不误伤其它文本；裸 JWT 字面量被替换；**`logger.info("token=%s", token)` 形态（args 脱敏）**；filter 恒返回 True（记录不被丢弃）。
- **configure_logging 与访问日志中间件（19 项）**：格式按 `APP_ENV` 推导（production→json / development→text）与 `LOG_FORMAT` 显式覆盖；非法级别回落 INFO 不抛错；JSON/文本输出可断言；**幂等**（重复调用只留一个自装 handler）；**不触碰他人 handler**（保护 pytest 等外部集成）；uvicorn 三个 logger 被收编到 root（且 `uvicorn.access` 压到 WARNING，避免与中间件重复输出）；root 级别生效；出口过滤器端到端生效。中间件侧（探针 FastAPI 应用 + httpx ASGITransport）：一条访问日志含 method/path/status_code/duration（数值型且 ≥0）；非 `/api/v1` 路径（`/`）同样记录；带 Token 时 user_id 取自 JWT `sub`、无 Token/非法 Token 为 `null`；Authorization 原文不落日志；**user_id 经 ContextVar 传给请求内下游日志且在请求结束后还原**；未处理异常记 `status_code=500` 后继续上抛；`LOG_REQUESTS=false` 时零输出；`duration` 反映真实耗时（50ms 慢处理下 ≥40ms 且不超过总耗时）。

**测试环境要点**：pytest 默认将 root logger 级别设为 WARNING，断言 INFO 级日志的用例必须给目标 logger 显式 `setLevel(INFO)`——否则会「空输出」假通过（本文件已修正两处）。测试套件默认 `LOG_REQUESTS=false`（`tests/conftest.py` autouse，与 `rate_limit_enabled` 同套路）。

## Request ID（TASK-057）

`tests/test_request_id.py`，**34 项**，全离线（不依赖 DB / Redis；仅 4 项走真实 `app.main`，其中一个 401 用例在认证依赖里提前返回、不触库）。分四层：

- **`resolve_request_id` 纯函数（13 项）**：无头时生成 uuid4 hex 形态；两次生成互不相同；**自生成值必然能通过白名单**（否则「回传的 id 客户端下次传回来会被丢弃」）；合法客户端值原样接受（含 traceparent 风格、前后空白 strip 后接受、恰好 64 字符的边界）；**10 类非法值一律丢弃并重新生成**——超长、空格、字符集外、分隔符、路径穿越样式、HTML、非 ASCII、`\n`、`\r\n`、`\x00`（其中换行/CRLF 是**日志注入**：能让一行日志变成两行）；空串/纯空白同样重新生成。
- **中间件契约（8 项）**：无头请求 → 响应头为服务端生成的 32 位 hex；客户端合法值 → 响应头原样回传；客户端非法值 → 响应头**不是**脏值而是新生成；两个请求 id 不同；请求内下游代码经 ContextVar 能读到同一个 id；请求结束后 ContextVar **还原为 null**（避免同 worker 下一个请求串号）；§26 错误信封（404）响应**也带**响应头；错误响应体形状未变（仍只有 `detail`）。
- **与其它中间件协作（4 项）**：最外层嵌套下访问日志的 `request_id` 与响应头一致（客户端传入 / 服务端生成两种路径各一条）；两条请求的日志 id 互不相同；**未处理异常的已知边界**——500 响应**没有** `X-Request-ID` 头（Starlette 的 `ServerErrorMiddleware` 在本中间件之外渲染），但访问日志里 `status_code=500` 与 `request_id` 都在（§34 的硬要求是「日志中必须带」，此处不破）。
- **真实应用（4 项）**：`app.main` 的中间件注册顺序里 `RequestIdMiddleware` 必须**最外层**（早于 `RequestLoggingMiddleware`）——顺序被调换就会让访问日志丢掉 request_id；`GET /` 带服务端生成的响应头；客户端传入值被原样回传；`GET /api/v1/users/me` 未认证 → 401 同时带响应头、信封与 `WWW-Authenticate` 均未被改动。

**测试写法要点**：HTTP 头的值在协议层是 latin-1 字节，Starlette 按 latin-1 解码——因此「客户端传非 ASCII」在中间件眼里是 latin-1 乱码。构造探针请求时必须把值按 **UTF-8** 编码成原始字节（忠实模拟线上），否则非 ASCII 用例会在构造阶段就抛 `UnicodeEncodeError`、**永远测不到这条路径**。

## 生产 compose 契约（TASK-059）

`tests/test_prod_compose.py` — **26 项**，全离线（**不启动 Docker**，CI 可直接跑）：解析 `docker-compose.prod.yml`，把「生产必须成立的性质」固化成断言。这类配置最容易被后续改动**静默**破坏——最典型的是「复制粘贴开发 compose」：一旦开发版把 5433/6389 发布到宿主、把 DB 密码当可选项的写法混进生产文件，数据库就直接暴露了，而当时不会有任何测试报警。

- **文件与项目隔离（6 项）**：文件存在且可解析；顶层项目名 `taskflow-prod`（必须区别于开发栈——开发版无顶层 `name`，项目名回落为目录名，同名就会共用 `task-flow_postgres_data` 并连到开发库）；服务集合 = 开发栈四服务 **+ nginx**（TASK-060 起，§31 要求生产含反代）；开发栈每个服务在生产都存在；不硬编码 `container_name`（否则与开发栈同名容器冲突且阻碍扩容）；本项目自建镜像用独立 tag 且非 `latest`（只比较带 `build:` 的服务——`postgres:16` / `redis:7` 是官方镜像，两套栈共用同一 tag 属正常）。
- **端口暴露面（4 项）**：postgres / redis **没有 `ports`**（Redis 无认证、数据库不该对外）；**除 nginx 外任何服务都不得发布宿主端口**（TASK-060 起 app 的 `127.0.0.1:8000` 已被删除——保留回环端口会让同机进程绕过反代直连应用并伪造 `X-Forwarded-For`），对外端口为 `${NGINX_HTTP_PORT:-80}`；**禁止 `env_file`**——宿主 `.env` 的 `DATABASE_URL` / `REDIS_URL` 指向 `127.0.0.1:5433` / `127.0.0.1:6389`，注入容器会覆盖 compose 里正确拼好的容器内地址（服务名），容器随即连不上任何东西，排查成本极高。
- **生产环境变量（8 项）**：`APP_ENV=production` 且 `LOG_FORMAT` 默认仍为 `auto`（在 production 下解析为 JSON，§33）；`DEBUG=false`（关闭 SQL echo 与 FastAPI debug）；`LOG_REQUESTS` / `RATE_LIMIT_ENABLED` 为 true；两个必需密钥用 `${VAR:?}` 必填语法且**无 `:-默认值` 回落**（只在**非注释行**上检查——注释里解释「不要沿用 change-me」是合法的）；传给容器的每个环境变量名都能在 `Settings.model_fields` 中找到（拼错名字不会报错，只会静默按默认值运行，是「配置不生效」类故障的根源）；worker 与 app 的环境变量完全一致（锚点复用，防「改了 app 忘了改 worker」）；`.env.example` 含生产必填项。
- **持久化与存储（3 项）**：三个状态卷都在顶层声明并被正确挂载（`postgres_data` / `redis_data` / `attachment_storage` → `/app/storage`）；**无宿主源码 bind mount**（生产镜像自带代码，挂宿主目录不可复现）；Redis `--appendonly yes`（Celery Broker 队列需跨重启存活）。
- **运行保障（5 项）**：四服务都有健康检查；app / worker 的 `depends_on` 用 `service_healthy`（只等「启动」会让 app 在库就绪前连库失败）；`restart: always`；四服务都配容器日志轮转（`json-file` + `max-size` + `max-file`）；worker 有 `stop_grace_period` 且启动命令采用可配置并发 `${CELERY_CONCURRENCY:-4}`。

**容器冒烟（真实 Docker，非 pytest）**：`docker compose -f docker-compose.prod.yml --env-file .env up -d --build` → 四服务 healthy；`docker port` 实证 app 只有 `127.0.0.1:18080->8000`、postgres / redis 无任何宿主端口；卷为 `taskflow-prod_*` 前缀，同时开发栈保持 healthy（两套栈并存互不影响）；`run --rm app alembic upgrade head` 迁移全部生效 → `/health` 返回 `env=production` / `database=up` / `redis=up`；注册 201 → 登录 200 → `/users/me` 200；容器日志为 §33 的 JSON 十字段（含 `request_id`、`user_id`，且无 SQL echo）；原始 socket 连接 `192.168.1.84:18080` **超时**（反证仅回环可达；用 socket 而非 urllib 是为了绕开环境代理）；`redis-cli config get appendonly` → `yes`；`down -v` 后生产容器与卷零残留、开发栈不受影响。另验证了两条**失败路径**：缺失 `POSTGRES_PASSWORD` / `JWT_SECRET_KEY` 时 compose 报 `required variable ... is missing a value` 且退出码为 1。

## Nginx 反代与真实客户端 IP（TASK-060）

TASK-060 的交付物一半是**配置**（nginx.conf / compose 接线），一半是**应用逻辑**（客户端 IP 判定）。配置类的错误不会让服务起不来，只会让安全属性**静默**消失，因此两层都做成离线可跑的契约测试。

### 客户端 IP 判定（`tests/test_client_ip.py`，26 项，全离线）

- **配置解析（8 项）**：`TRUSTED_PROXY_IPS` 支持单个 IP（自动补 `/32`）、CIDR、IPv6 网段、逗号分隔与空项；`172.28.0.5/24` 这类主机位非零的写法按网段处理；非法项**跳过而不抛错**（一个笔误不该让服务起不来）；解析结果被 `lru_cache` 缓存（该函数在请求路径上被调用，不能变成每请求开销）。
- **判定逻辑（11 项）**：开关关闭时完全忽略该头（与 TASK-046 行为一致）；对端在信任网段内才采信；对端不在网段内不采信；**开关打开但网段为空 → 不采信**（fail-safe：配置错误退化为「安全但限流不准」，绝不退化为「信任任何人」——那是让攻击者靠伪造该头把限流拆成无限份）；多值一律拒绝（本项目是单层反代，覆盖写入应当只有一个值，多值意味着有环节在追加）；非法/空/缺失值回落到对端地址；空白会被裁剪；IPv6 客户端地址可用；**IPv4-mapped IPv6 归一**（`::ffff:172.28.0.5` → `172.28.0.5`，否则 `in IPv4Network` 恒为假，出现「配置看起来对、信任却永远不生效」的静默失效——该缺陷由本 TASK 测试捕获，初版只归一了采信路径、漏了回落路径）；对端不可知时给占位值且**绝不**用客户端可控的头填充。
- **安全默认（1 项）**：`TRUST_PROXY_HEADERS` 默认 false、`TRUSTED_PROXY_IPS` 默认空，且 `APP_ENV=production` 本身**不会**打开信任（不能用环境名暗中改变信任边界）。
- **中间件接入（6 项）**：`_client_ip` 在信任开关两种状态下的取值；无 `client` 的请求不崩；访问日志含 `client_ip` 字段；信任生效时日志记的是**真实客户端**而非 Nginx；信任关闭（或对端不在网段）时伪造的头既不改变限流身份也不污染审计日志。

### Nginx 配置与生产接线契约（`tests/test_nginx_config.py`，32 项，全离线）

所有「不得出现」的断言只看**去掉注释后的正文**——注释里会引用反面写法（例如说明为什么不能用 `$proxy_add_x_forwarded_for`）；指令取值一律经空白归一，避免断言被无关的格式改动打破。

- **结构与 §31 职责（11 项）**：`nginx/nginx.conf` 存在（§4）；括号配平；`events` / `http` / `server` / `upstream app_backend` 齐备；upstream 指向的必须是 compose 里**真实存在**的服务名且端口与应用监听端口一致（写错就是每个请求 502）；`proxy_pass` 只有一个目标；只 `listen 80`、无任何 `ssl_certificate`、**不发 HSTS**（纯 HTTP 上发 HSTS 既无效又误导——证书不进仓库，TLS 由上游终止）；`client_max_body_size` **严格大于**应用 `MAX_UPLOAD_SIZE`（颠倒过来会让超限上传拿到 nginx 的 HTML 错误页而不是 §26 的 JSON 信封）；六个超时指令齐备；日志输出到 `/dev/stdout` / `/dev/stderr` 且格式含 `$http_x_request_id`。
- **安全（7 项）**：`X-Forwarded-For` 必须是 `$remote_addr`（**覆盖**语义）且正文里不得出现 `$proxy_add_x_forwarded_for`（追加语义会让客户端自带的值排到链首，限流与审计同时失去可信度——本 TASK 最关键的一条断言）；`X-Forwarded-Proto` / `X-Forwarded-Host` 齐备；`Host` 用 `$host` 而非 `$http_host`（后者透传客户端任意 Host）；`X-Request-ID` 透传（两层日志可凭同一 id 串联）；三个安全头都带 `always`（否则 4xx/5xx 不带）；`server_tokens off`；**无任何静态文件服务指令**（`alias` / `root` / `autoindex` / `X-Accel-Redirect`）且正文不出现附件目录——一旦出现，私有附件的鉴权链（TASK-043）就被完全绕过（IDOR）；`Connection` 置空以配合 upstream keepalive。
- **生产接线（14 项）**：nginx 服务存在、镜像 tag 固定版本（非 `latest`）；**除 nginx 外没有服务发布宿主端口**（这是「该头值得信任」的结构前提）；app **没有** `ports`；nginx 配置以 `:ro` 挂载；nginx 等 app healthy 再启动；健康检查探 nginx 自有的 `/nginx-health`（不探 `/health`，否则「入口挂了」与「后端重启中」互相污染）；app 命令是 `gunicorn` + `uvicorn.workers.UvicornWorker` + 可配置 `--workers`；**不开** Gunicorn 自带访问日志（避免与应用的 §33 访问日志重复——TASK-056 在 uvicorn 上踩过的坑）；`--graceful-timeout=30` 与 compose `stop_grace_period: 30s` 对齐；**`TRUSTED_PROXY_IPS` 必须等于 compose 声明的子网**（交叉校验：改一处忘了改另一处会直接失败，这是防止信任静默失效的唯一办法），且该子网是私有段且不撞 Docker 常用默认段；`FORWARDED_ALLOW_IPS` 置空（让应用成为客户端 IP 的唯一判定点）；开发栈**不得**开启 `TRUST_PROXY_HEADERS`；`.env.example` 记录了四个相关配置项。

### 容器冒烟（真实 Docker，非 pytest）

见下方 PROGRESS 的 TASK-060 条目：`docker port` 实证只有 nginx 对外、宿主经 nginx 访问全链路可用、`X-Forwarded-For` 覆盖行为与信任网段的实测对照、Gunicorn+UvicornWorker 生效、附件下载仍走鉴权。

## CI workflow 契约（TASK-061）

`tests/test_ci_workflow.py` — **35 项**，全离线（不联网、不跑 Actions）：解析 `.github/workflows/ci.yml` 并交叉校验它引用的 `Dockerfile` / `requirements*.txt` / `pyproject.toml` / 两个 compose 文件，把「CI 必须成立的性质」固化成断言。

理由是这类文件的错误**只在推送几分钟后**才以「红的 run」出现，而那条反馈路径足够慢，慢到让人养成「再跑一次试试」的习惯。最要紧的两条性质：**service 端口必须匹配测试里硬编码的地址**（40 个测试文件写死了 `127.0.0.1:5433` / `127.0.0.1:6389`，CI 的映射一旦被改，全量用例集体连接失败——而这件事本地跑不出来），以及**迁移可逆性步骤必须真的在跑**（`downgrade()` 的腐坏平时无人察觉）。

- **文件、触发与权限（8 项）**：workflow 位于 §4 指定的路径；可解析且声明了 `name`；`push` 与 `pull_request` 都触发到 `master`（只管 push 则 PR 无门禁，只管 PR 则直推 master 无人拦）；支持 `workflow_dispatch`（排查偶发失败不必造空提交）；**不使用 `pull_request_target`**（该事件在目标仓库上下文里运行、含 secrets，却由外部 PR 内容触发，是常见提权路径）；`permissions` 仅 `contents: read`；`concurrency` 取消同分支旧 run；**每个 job 都有 `timeout-minutes`**（默认上限 360 分钟，一个卡住的 job 会白占六小时）。
- **job 与步骤顺序（6 项）**：三 job 集合；lint 先装依赖再 `ruff check`（没装 ruff 就跑它以 127 失败，报错毫无信息量）；test 的三段按「装依赖 → 迁移 → pytest」（迁移排在 pytest 之后或缺失，用例会跑在没有表的库上，症状是一堆 `UndefinedTableError`，与真实原因隔得很远）；docker-build 用根 Dockerfile、tag 显式且非 `latest`；**CI 的 Python 版本从 Dockerfile 反向读出并比对**（两处漂移的后果很隐蔽：CI 全绿而生产镜像是另一个 Python 大版本）；lint / test 都装 `requirements-dev.txt`。
- **lint 可复现性（4 项）**：`requirements-dev.txt` 里 ruff 用 `==` **钉死版本**（用 `>=` 则「这次提交能不能过 lint」取决于 CI 当天装到哪个版本，同一份提交时红时绿）；dev 依赖以 `-r requirements.txt` 扩展而非重抄一遍；**ruff 不得出现在 `requirements.txt`**（那是 Dockerfile 装进生产镜像的文件）；`[tool.ruff.lint] select` 显式声明且 `target-version` 与镜像一致（实测不写 `select` 报 219 项、写成本集报 36 项，依赖默认值等于把门禁交给 ruff 的版本决定）。
- **service 端口契约（11 项）**：service 镜像与两个 compose 里的**同名同 tag**；**测试硬编码的每个端口都有 service 监听**（核心断言）；端口映射的**目标**端口也对（只断言宿主端口的话，「把 5433 映射到 redis 的 6379」这种错位仍会通过）；反向断言**不提供测试用不到的端口**；`REQUIRED_SERVICE_PORTS` 自身也不得腐坏（清单里每个端口在 `tests/` 中确有引用）；`tests/` 里出现的端口要么需要服务、要么登记在「已知例外」里（`1` / `6399` 是刻意用来验证 Redis 不可用降级的端口，`8000` 只出现在说明文字中）——这是**防漂移**：将来有人引用第三个端口时 CI 会红，逼他明确决定是加 service 还是登记为例外；例外清单不得与必需端口重叠（否则等于用一个标签悄悄豁免了核心断言）；两个 service 都有 `--health-cmd` / `--health-retries`（没有健康检查时，容器一起来就跑，安装依赖的几十秒**通常**够 Postgres 就绪，于是这变成一个「多数时候能过」的偶发失败）；`DATABASE_URL` / `REDIS_URL` 的端口与 service 映射一致（两处是同一件事的两种写法，漂移后症状与「service 没起来」几乎一样）；`DATABASE_URL` 必须是 `postgresql+asyncpg://`（写成同步驱动会在创建引擎时失败，报错与「连接串写错」相差很远）。
- **配置等价性（3 项）**：CI 传的每个环境变量名都是真实的 `Settings` 字段（拼错如 `DATABSE_URL` 不会报错，只会静默按默认值运行，于是 CI 去连 `postgres:5432`，失败信息看起来像「service 没起来」）；环境变量集合**恰好**是那三个「默认值在本环境不可用」的项（`DATABASE_URL` / `REDIS_URL` 的默认值是 compose 服务名，`JWT_SECRET_KEY` 默认 `change-me`）——断言「恰好」而非「包含」，多出来的键会引入第三种配置，让「CI 绿 ⇒ 本地绿」悄悄失效；设了的值必须真的改掉容器服务名（若把 `DATABASE_URL` 又抄成 `postgres:5432`，这个变量就形同虚设，且端口断言仍会通过）。
- **迁移可逆性（2 项）**：三步命令与顺序为 `upgrade head` → `downgrade base` → `upgrade head`（§37）；三步写在**同一条 shell** 里并 `set -euo pipefail`（拆成三个 step 时若失败被吞，后续在旧库上继续，会呈现出「pytest 通过」的假绿）。
- **不发布镜像（1 项）**：正文不得出现 `docker push` / `docker/login-action` / `ghcr.io` / `packages: write`——一个纯粹回答「能不能构建」的步骤不该带上发布凭据。

**已知边界**：本文件依赖 `.github/workflows/ci.yml` 这个**仓库文件**存在（CI 与本地都满足），所以在「只有应用代码」的环境（如生产镜像）里跑不全——那类环境本来也不跑测试。

### 真实验证（非 pytest）

- **迁移三步在「无 `.env`」下跑通**（本 TASK 最重要的一次实证）：用真实应用镜像起容器，**仅靠环境变量**把 `DATABASE_URL` 指向一次性探针库，跑 `alembic upgrade head` → `downgrade base` → `upgrade head`：三步 exit 全 0、业务表数 **16 → 0 → 16**；容器内 `ls -a /app` 实证**没有 `.env`**（前提成立）。这一步不能只靠本地——本机**永远有 `.env`**，所以「没有 `.env` 时 alembic 还能不能跑」这条 CI 的既有路径从未被覆盖过（`.env` 已被 `.dockerignore` 排除）。
- **docker build**：按 CI 的命令 `docker build --tag taskflow-app:ci .` 执行，exit 0、镜像产出（9 步全绿）；验证后删除该镜像。
- **配置等价性核查**：逐字段对比本机 `.env` 与 `Settings` 默认值，真正的差异只有三处，CI 恰好显式设了这三个——CI 与本地只差「谁提供 Postgres / Redis」。
- **本地跑同一套 lint**：`pip install -r requirements-dev.txt && ruff check .`。注意本机 PyPI 清华镜像**没有 ruff**，需指定官方源（见 DEPLOYMENT.md）。

**运行首跑结果**：GitHub Actions run #1（推送 `594bf53` 后自动触发）**三个 job 全部 success**，用时约 3m14s。`Tests (pytest)` 的步骤序列为 `Initialize containers` → `Install dependencies` → `Verify migrations are reversible` → `Run full test suite`——即 service 端口映射、环境变量与迁移三步在真实 runner 上与本地一致地成立。

## 覆盖率基线与质量契约（TASK-062）

质量检查的完整结论（含 §57 逐条对照、偏差与未完成项）见 **`docs/QUALITY.md`**；本节点说明测试侧的产物与命令。

### 覆盖率工具与基线

- `pytest-cov==7.1.0` 进 `requirements-dev.txt`（**不进** `requirements.txt`：那是 Dockerfile 装进生产镜像的文件）。与 ruff 同样的问题——本机 PyPI 清华镜像没有它，安装需指定官方源 + 代理。
- 配置在 `pyproject.toml`：`[tool.coverage.run]`（`source = ["app"]`、`branch = true`）+ `[tool.coverage.report]`（`show_missing = true`、`exclude_also = ["def __repr__"]`）。**CI 不传 `--cov`、不设 `fail_under`**——本轮测量的目的是「找出值得补的分支」，而不是维持一条数字线；设阈值会催生为达标而写的空测试（Phase 14 明确告诫）。
- 命令：`pytest -q --cov --cov-report=term-missing`。
- **基线（2026-09-16，TASK-095 重测）**：**1207 passed**（TASK-081~085 增量 14 项：注册默认角色 2 项、RBAC 管理端点 10 项、用户搜索 2 项；TASK-088 增量 18 项：护栏反向用例 2 + 健康探针族 `tests/test_health.py` 16；TASK-089 增量 17 项：`tests/test_beat_schedule.py` 11 + 归档表终态清理 3 + beat compose 契约 3；TASK-090 增量 14 项：`tests/test_metrics.py`——指标端点契约、路由模板标签基数、500 统一信封与 request_id 日志关联、采集器健壮性；另随新契约更新 3 处原子性用例——未捕获异常改断 500 信封；TASK-091 增量 11 项：`tests/test_config_production_guards.py`——四类生产错配拒绝用例（报错点名配置项）、合法配置放行、开发环境不检查、收集式全量点名、两条真实子进程端到端；TASK-092 增量 9 项：`tests/test_docs_consistency.py` 扩充——端点声明 ↔ OpenAPI/nginx 漂移检测（含 `/api/v1` 前缀/参数占位豁免、`GET|POST` 复合写法逐方法核对）与 README 健康探针族集合断言，全部为合成反向用例；TASK-093 增量 32 项：`tests/test_tenant_model.py` 新建——离线模型断言、DB 约束集成（slug UNIQUE、CHECK 拒绝非法状态/slug/配额）与平台管理端点端到端（创建/详情/列表分页/部分更新/状态机白名单/终态 409/slug 冲突 409/403/404），另同步 5 处 RBAC 种子计数 22 → 23；TASK-094 增量 39 项：`tests/test_tenant_columns.py` 新建——元数据断言、真实库结构断言、跨租户同名正反用例、FK RESTRICT、DB DEFAULT 桥接、回填幂等与零孤儿、ContextVar 注入优先，另同步 12 处既有用例（列集/唯一约束/附件 key/存储根目录）；TASK-095 增量 32 项：`tests/test_tenant_isolation.py` 新建——离线接线（mixin 归属、bypass 出口审计）、应用层统一作用域（ORM SELECT 自动过滤 / 无上下文不过滤 / 显式出口放开 / flush 注入与显式赋值优先）、事务级 GUC（after_begin 按上下文写入、跨事务持续、enforce_tenant_guc 翻转已开启事务）、ContextVar 并发不串号、RLS SET ROLE 实证（fail closed / WITH CHECK 拒越租户插入 / 越租户 UPDATE 零行 / bypass 放行）、API 越权矩阵 8 端点 × A→B 全 404 + 正向对照），另补 3 项分支单测（非 PG 方言早退、bypass GUC 文本、enforce no-op 路径）），全量 2948 语句 / **7 未覆盖** / 458 分支 / 3 分支半覆盖 → **99.76% 行、99.34% 分支**。
- 五处未覆盖行：`app/services/attachment.py:179`（`_UploadReader.readable()`，starlette 协议要求的纯声明式方法，属**刻意不测**——为数字而测无业务价值的代码被 Phase 14 明令禁止）；`app/services/auth.py:80` 与 `app/services/user.py:78` 为 TASK-088 重测新暴露的存量缺口（防御分支 / 缺失的 404 用例）；`app/core/metrics.py:171-172` 为导入兜底分支（函数层面已等价覆盖）。

### 新增测试模块（4 个，80 个用例）

- `tests/test_storage_guards.py`（**42 项**，离线）：存储层安全边界的单元测试——`validate_key` 各条拒绝规则、`build_key` 后缀归一化、`LocalStorageBackend` 的结构层越界断言、超限时清理半成品、删除幂等、空目录回收。其中一条把「盘符规则在当前字符集下不可达」这一事实**写成可执行断言**（放松字符集后该规则仍会触发），使这条纵深防御分支既被覆盖、其不可达性也被记录。
- `tests/test_quality_gaps.py`（**24 项**）：把覆盖率排查中「有价值但未覆盖」的分支补齐——附件落库失败时**回滚事务 + 删物理文件**的双重一致性、注册的并发 409、非 owner/admin 移除成员 → 403、可见性判定、通知派发失败**吞掉但记日志**、限流关闭时零 Redis 往返、lifespan 释放连接池、`/health` 依赖挂掉时降级 200、跨项目「我的任务」数据原语，以及 TASK-062 收尾补的 8 项（文件名净化空输入/不可用扩展名截断、非超限存储故障原样上抛、`Retry-After` 下界、可信代理判定的 fail-safe、非 `/api/v1` 路径零限流开销、限流身份降级为 IP、访问日志 `user_id` 对畸形 Token 记 null、登出在无可用 jti 时零写操作、删除根级对象不误删存储根）。
- `tests/test_quality_checks.py`（**12 项**，全离线）：把「架构与质量必须成立的性质」变成**静态断言**（AST 解析 + OpenAPI schema 内省）——Router 不得 import CRUD、Model 不得反向依赖上层、Router 不得直接构造 SQL、Service 不得依赖 HTTP 传输类型（唯一豁免 `UploadFile`，且白名单化）、**全模型零 `relationship()`**、全部出参 schema 无密码字段、每个 `AppError` 子类都声明具体 4xx、`AppError` handler 已注册且渲染 `{"detail": ...}`、所有带 `limit` 的端点必须 `le=100` 且默认值不超上限、`skip` 必须 `ge=0`、`Settings` 的**声明默认值**不含真实密钥。
- `tests/test_query_efficiency.py`（**2 项**）：N+1 的**运行时**护栏——用 SQLAlchemy `before_cursor_execute` 事件统计 SELECT 条数，断言 3 个任务与 12 个任务的列表请求**语句数相等**，且访问 `task_assignees` 的语句恰好 1 条并含 `IN (`。与上一条的静态断言互补：静态侧挡住「加回 `relationship()`」，运行时侧挡住「把批量查询拆成循环里的单条查询」（后者不新增任何 `relationship()`，静态检查看不见）。

### 非 pytest 的验证

- **开发库零残留复核**：全量运行后用 SQL 直查 13 张业务表，**全部 0 行**。该复核**发现并修复了一处此前未被察觉的污染**——`operation_logs.user_id` 刻意无外键（TASK-039 决策：审计日志要比用户活得久），因此不会被 `delete(User)` 级联清理。残留 507 行（全为 `task:transition`）；逐文件测量进一步定位到**三个**泄漏源：`tests/test_task_transition_api.py`（主犯）、`tests/test_notification_api.py`（每轮 2 行）、`tests/test_notification_e2e.py`（每轮 1 行）。三者 teardown 已补齐并清空存量孤儿行，复测均 leaked=0（见 DECISIONS 044）。
- **`ruff check .`** → `All checks passed!`（exit 0，与 CI 的 lint job 同一条命令）。

## 任务搜索索引与全文检索列（TASK-064）

落实开发文档 §14 / §57 的 `pg_trgm` 与 `tsvector`。完整决策与踩坑记录见 `docs/DECISIONS.md` 的 Decision 045。

### 三层断言（`tests/test_task_search_indexes.py`，14 项）

「加了一个索引」与「索引真的被用上」是两件事，所以分三层钉：

1. **离线声明层**（不需数据库）：生成列是 `persisted=True` 的 `Computed` 且表达式含 `to_tsvector('simple'` 与 title/description 两侧；`insert(Task).values(...)` 的编译结果**不含** `search_vector`（应用只读的静态保证）；两个索引在 Model 上声明为 GIN、其中 title 带 `gin_trgm_ops`。
2. **真实落库层**：`pg_extension` 有 `pg_trgm`；`information_schema` 显示该列 `data_type='tsvector'` 且 `is_generated='ALWAYS'`；`pg_indexes` 定义含 `USING gin (search_vector)` 与 `gin_trgm_ops`；插入任务后 DB 自动填充向量且 **description 也在里面**；改标题后向量**自动重算**（证明无需 Service 维护）。
3. **执行计划层**：`EXPLAIN` 实证 `ILIKE '%login%'` 走 `ix_tasks_title_trgm`、中文 `ILIKE '%登录缺陷%'` 同样走它、`search_vector @@ to_tsquery(...)` 走 `ix_tasks_search_vector`。

### 两个必须知道的写法约束

- **`EXPLAIN` 前一律 `SET LOCAL enable_seqscan = off`**。测试库 `tasks` 通常只有个位数行，这种规模下优化器**必然**选择顺序扫描——直接 EXPLAIN 会得到「索引没被用」的**假阴性**。排除顺序扫描后验证的是「索引对该查询形状**可用**」（这才是指针存在的意义）；真实数据量下选不选它是优化器的成本决策。
- **编译查询要用 asyncpg dialect**（`postgresql.asyncpg.dialect()`）。用 psycopg2 dialect 编译 `literal_binds` 会把 `%login%` 转义成 `%%login%%`，塞进 `text()` 不会还原——双写通配符在 LIKE 语义下恰好等价，于是测试**看起来是绿的**，但断言里的 SQL 与被测 SQL 已对不上号。

### 中文边界（`test_chinese_substring_matches_ilike_but_not_the_full_text_index`）

把「`keyword` 继续走 `ILIKE` 而不是 `search_vector`」的**依据**固化成断言：`to_tsvector('simple')` 不做中文分词，`修复登录缺陷` 会成为**单个 token**，于是 `to_tsquery('simple','登录')` 命中 **0** 条、`ILIKE '%登录%'` 命中 **1** 条。将来若有人把 keyword 改到 tsvector 上，中文子串检索会静默失效，这条断言会立刻变红。pg_trgm 按字符组切分、与语言无关，这才是中文场景可用的组合。

### 语义未变的守护

`test_keyword_filter_still_matches_substrings_case_insensitively`：直接调 CRUD 的 `list_tasks_by_project(keyword=...)`，断言仍是**大小写不敏感的标题子串匹配**且只命中一条——本 TASK 只加索引、不改查询。接口层的 keyword 契约由 `tests/test_task_query_api.py`（TASK-035）覆盖。

## 进度文档一致性护栏（TASK-064）

`docs/PROGRESS.md` 的回写**四次**出现「编辑报成功但内容没落盘」（TASK-048 / 049 / 051 / 062），表现为 `## Current Task` 更新了、而 `## Completed` 与 `## Next` 停在上一轮。它不报错、不影响任何测试，唯一表现是文档说谎。因此把「核验」变成可执行断言：

- **`scripts/check_docs.py`**：手动执行的一致性检查，退出码 0/1 并逐条打印矛盾。校验 6 条不变量——`## Current Task` 以 `TASK-NNN` 开头且该任务在 `docs/TASKS.md` 中存在**并已勾选**；`## Completed` 与 TASKS.md 的已勾选任务**集合与顺序都相同**；**`## Completed` 的最后一条就是 `## Current Task`**（这是四次事故的直接探针）；`## Next` 指向 TASKS.md 中**第一个未勾选**任务；`## Current Phase` 与 Current Task 所属 Phase 一致；结构坏掉不得静默通过。
- **`tests/test_docs_consistency.py`（12 项）**：第一层断言**仓库真实的两个文档一致**（CI 已在跑 pytest，等于自动门禁）；第二层用**合成文档**构造 9 种矛盾，断言检查器**真的会报出来**。第二层不能省——没有它，一个「永远返回空列表」的假检查器也能让第一层通过（即本项目在 `test_missing_idempotency_key_generates_one` 上踩过的假绿）。
- **取舍**：纯文档问题从此也会让 CI 变红。这是有意的：该问题的历史成本高于偶尔一次红的打扰。

### 非 pytest 的验证（TASK-064）

- **迁移可逆性（CI 等价）**：在**一次性探针库**上复现 CI 的三步 `alembic upgrade head → downgrade base → upgrade head`，三步均 OK；往返后 16 张业务表齐全、`search_vector` 为 `tsvector`、`pg_trgm=1.6`、tasks 的 5 个 `ix_tasks_*` 索引全部存在。探针库用完即删（`DROP DATABASE ... WITH (FORCE)`），**开发库未参与**——比在开发库上跑 `downgrade base` 安全得多（那会连 RBAC 种子一起拆掉）。
- **执行计划人工复核**：除测试断言外，另在 `plan_cache_mode` 的 `auto` / `force_custom_plan` / `force_generic_plan` 三种取值下确认绑定参数形式都能用上索引（生产默认是 `auto`）。

## README / 面试文档护栏（TASK-063）

README 是仓库门面，也是**最容易悄悄说谎**的文档——它描述「项目现在长什么样」，而项目一直在变。TASK-064 为 `PROGRESS.md ↔ TASKS.md` 建的机制，在 TASK-063 扩展到 README 与 `docs/INTERVIEW.md`。

分工：`scripts/check_docs.py` 是**人的入口**（只读文本与文件系统，不连库不上网，可随时跑）；`tests/test_readme.py` 是 **CI 门禁**，并且能做检查器做不到的事——导入 app 取 **ORM `metadata`** 与 **OpenAPI schema**，把 README 的结构性声明与**代码事实**对齐（两份文档可以一起错，代码不会）。

- **规格一致性**：README 必须包含规格 §Phase 17 列出的全部 19 个部分（清单从开发文档的代码块里解析，不在这里重抄一份）；`docs/INTERVIEW.md` 必须覆盖 §56 的 9 个领域 35 个问题，且**题干逐字一致**——改写题干是危险的，因为它让「其实是另一个问题」蒙混过去。
- **跨文档一致**：README 的**进度前沿**（`TASK-001 ~ TASK-NNN 全部交付`）对齐 `TASKS.md` 的已勾选最大编号；**当前 Phase** 对齐 `PROGRESS.md` 的 `## Current Phase`；**基线数字**对齐 `QUALITY.md`——靠「当前基线」这个关键词定位（历史数字可以留在文中，不会被误判）。
- **与代码事实一致**：表 / 外键 / 唯一约束 / CHECK 数对齐 `Base.metadata`；操作数与 `/api/v1` 路径数对齐 `app.openapi()`；目录下的模块数、迁移数、测试文件数对齐文件系统；README 内相对链接必须能解析到真实文件。
- **代价是明确的**：这些数字一变 CI 就会红（新增一个迁移或测试文件都要顺手改 README）。这是**有意**的取舍——README 数字静默失真正是本项目反复吃亏的失败模式，一次红的打扰远低于一篇说谎的 README。同理，`MIGRATION_COUNT_RE` / `TEST_FILE_COUNT_RE` 被断言「仍能在 README 中匹配到」，否则改一句措辞就能悄悄关掉一条检查。
- **不空转的保证**：`tests/test_readme.py`（**27 项**）用**合成文档**构造 12 种矛盾，逐条断言检查器真的报错——没有这一层，「仓库一致」那条断言被一个永远返回空列表的检查器就能骗过。

`tests/test_docs_consistency.py` 同步补了 2 项：**全部任务勾完后 `## Next` 不许再指向任何 TASK**（TASK-063 收尾当天才会走到的分支，不处理就会静默通过），以及与之配套的正向用例。

## 完成条件
测试失败不能标记任务完成；不能虚构测试结果。
