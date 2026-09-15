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

## 完成条件
测试失败不能标记任务完成；不能虚构测试结果。
