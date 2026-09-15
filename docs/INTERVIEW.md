# TaskFlow Pro 面试技术难点

开发文档 §56 要求「项目完成后必须能够独立解释」九个领域、**35 个问题**。本文逐条作答。

写作原则：

- **每条答案都指向本项目的真实代码、决策编号或测试名**，不写通用八股。能被追问到
  「你怎么证明」的地方，都给出证据（文件名、测试名、实测结论）。
- **不掩盖缺口**。没实现、有残余风险、或者刻意不做的部分，明确写出来并说明理由——
  面试里「知道自己的系统哪里会坏、为什么不改」比「什么都做了」可信得多。
- 每条答案给一个 **一句话结论**，先讲结论再讲实现，便于按需展开或收敛。

配套文档：[`DECISIONS.md`](DECISIONS.md)（逐条决策）、[`QUALITY.md`](QUALITY.md)
（质量基线与已知偏差）、[`../README.md`](../README.md)（系统全貌）。

---

## FastAPI

### 1. FastAPI 为什么适合这个项目？

**一句话结论**：它同时提供「全链路异步」「依赖注入」「从类型注解自动生成校验与文档」，
正好对上本项目「异步 IO 为主 + 权限分层 + 40 个操作需要可读契约」的需求。

- **全链路 async**：路由 `async def`、数据库 asyncpg、Redis `redis.asyncio`。协作式 IO
  场景（等 DB / 等 Redis）下，单进程能同时承载大量请求。
- **依赖注入当授权链用**：`app/core/deps.py` 里 `CurrentUser = Annotated[User,
  Depends(get_current_user)]`，权限用依赖工厂 `require_permission("task:read")` 声明在
  路由上——权限是**声明式**的，新增端点漏写权限会被契约测试发现，而不是靠 review。
- **OpenAPI 即契约**：`/docs`、`/redoc`、`/openapi.json` 由路由与 Pydantic 模型生成，
  **不会与实现漂移**；测试可以直接读 `app.openapi()` 做断言（如逐端点检查 `limit ≤ 100`）。
- **代价**：FastAPI 不管 ORM、迁移、后台任务、连接池——这些都要自己选型并说清理由
  （SQLAlchemy 2.0 / Alembic / Celery）。换来的是每一层都可以被解释和替换。

### 2. Depends 做什么？

**一句话结论**：把「取得依赖」从函数体搬到函数签名上——框架负责解析依赖树、在**同一
请求内缓存**结果，并在依赖失败时中断请求。

- 链条（`app/core/deps.py`）：`HTTPBearer(auto_error=False)` → `get_current_user`
  （解析 `Authorization: Bearer`，把「取不到/不合法」统一表达为 401）→
  `require_permission(...)`（认证通过后追加授权判定，缺权限 403）。
- **`auto_error=False` 是刻意的**：FastAPI 的 `HTTPBearer` 默认在缺少 Authorization 头
  时抛 **403**，与本项目「认证失败 → 401 + `WWW-Authenticate: Bearer`」的规范冲突。
- 依赖工厂：`require_permission("a", "b")` 返回一个依赖函数（AND 语义），因此既能写成
  `dependencies=[Depends(require_permission("task:read"))]`，也能拿到用户对象。
- 值得强调的追问点：Depends 不只是「注入」，它是**分层的授权链**——认证（401）与授权
  （403）职责分离，且失败文案直接列出缺哪个权限名，便于定位。

### 3. async/await 如何工作？

**一句话结论**：单线程事件循环 + 协作式调度——`await` 是「把控制权交还事件循环」的
显式挂起点，因此一个进程能同时处理大量**等 IO** 的请求。

- 本项目：`create_async_engine`（asyncpg）+ `redis.asyncio`；`/health` 用
  `asyncio.timeout(2)` 给依赖探测设上限，避免探针把请求挂死。
- **边界（面试常追问）**：async 只加速「等待」，不加速「计算」。所以本项目把耗时可重试
  的工作（通知派发、日志归档、附件清理）**移出请求路径**交给 Celery，而不是在请求里
  假装异步。
- 反例：在 `async def` 里跑同步阻塞代码（大文件同步读写、重 CPU 计算）会阻塞**整个
  事件循环**，所有并发请求一起变慢。这与「用多线程」的失败方式不同，更难排查。
- 一个真实的 async 陷阱（本项目踩过）：asyncpg 连接池**绑定事件循环**，Celery worker
  里不能复用 API 进程的 engine 单例，否则报 `Event loop is closed`；`app/tasks/*` 因此
  每次调用新建短命 engine + 独立事件循环。

### 4. Pydantic 做什么？

**一句话结论**：它是「请求/响应的类型契约 + 校验 + 序列化」的执行者；校验失败由
FastAPI 统一转成 422。

- 本项目：`app/schemas/*` 分为请求与响应模型；枚举（`status` / `priority`）在 schema
  层就限死，非法值得到 **422** 而不是落到 Service 才炸。
- **安全性也在这里落**：响应模型**永不包含口令字段**。契约测试逐个扫描
  `app/schemas` 的所有模型，断言没有 password 类字段（`UserRead` 显式省略
  `password_hash`），从结构上杜绝「哪天顺手把 ORM 对象直接返回」导致的泄露。
- `pydantic-settings` 让**配置**也有类型与默认值；测试进一步断言**声明层默认值里不含
  真实密钥**（防止有人把真密钥写进 `config.py` 默认值）。
- 追问点：Pydantic v2 的校验核心是 Rust 实现（pydantic-core），与 v1 不是同一量级的
  性能与行为（严格模式、`model_validate` 等）。

---

## SQLAlchemy

### 5. SQLAlchemy 2.0 有什么变化？

**一句话结论**：从「隐式魔法」转向「显式类型」——模型、查询、异步都是显式的。

- **模型**：`Mapped[datetime]` + `mapped_column(...)`，类型即列定义，IDE/mypy 可读；
  本项目 16 个模型全部这么写。
- **查询**：统一 `select()` 2.0 风格，不再用 `session.query()`。附带好处是语句**可编译、
  可检查**——本项目的搜索索引测试就是把 SQLAlchemy 编译出的 SQL 拿去 `EXPLAIN`。
- **异步是一等公民**：`create_async_engine` / `async_sessionmaker`，不再依赖第三方补丁。
- 本项目特意设的两个会话参数：
  - `expire_on_commit=False`：提交后对象属性仍可读，避免「组装响应时触发隐式 IO」——
    在异步下隐式 IO 会直接抛错（而不是变慢）；
  - `autoflush=False`：flush 时机由我们决定，避免权限查询时意外把半成品数据刷进库。

### 6. Session 生命周期怎么管理？

**一句话结论**：一个请求一个 Session，请求结束即关闭；**事务边界在 Service**，不在
Router、也不在 CRUD。

- `app/db/session.py::get_db` 是 async generator 依赖：`async with
  async_session_factory() as session: yield session`——每请求一个会话，用完即关。
- **CRUD 只 `flush()`，不 `commit()`**。例如 `app/crud/operation_log.py` 是 flush-only，
  这样「业务写 + 审计写」才能落在**同一个事务**里（创建任务、状态流转都是这么做的）。
- Service 负责 `commit()`，异常时 `rollback()` 后抛领域异常（如 `register_user` 捕获
  `IntegrityError` → `rollback()` → 409）。
- **Celery worker 例外**：它没有请求概念，每次任务调用自建 engine + session + 事件循环
  （理由见 Q3 的 asyncpg 绑定事件循环）。
- 证据：`tests/test_task_crud.py`（CRUD 不提交）、端到端测试断言「业务回滚后审计不落库」。

### 7. ORM 和 SQL 有什么关系？

**一句话结论**：ORM 是 SQL 的**生成器**，不是替代品；用它的前提是你仍然能看懂它生成
了什么 SQL。

- 本项目敢用 ORM 是因为「能验证它」：
  - 运行时挂 `before_cursor_execute` 事件数 SELECT 条数（N+1 护栏）；
  - 迁移 autogenerate 后**人读 diff**再落盘（本项目用它对模型与库做过差异核对）；
  - 把编译出的语句送进 `EXPLAIN` 验证索引命中（搜索索引测试）。
- ORM 不替你做判断：「这条 WHERE 能不能用上部分索引」「这条 LIKE 能不能用 trigram」——
  这些只能靠执行计划回答。
- 一个具体例子：`ILIKE '%x%'` 在 B-tree 上无用（前缀不固定），要靠 `pg_trgm`。ORM 不会
  告诉你这件事，它只是忠实地把 `ilike` 翻译成 SQL。

### 8. 如何解决 N+1？

**一句话结论**：本项目选了 §46 明列的第三方案——**显式批量查询**，并把它变成可回归的
运行时断言，而不是靠「记得加 eager load」。

- **全项目零 `relationship()`**（有契约测试断言）。关联读取一律显式批量：如
  `app/crud/task_assignee.py::list_assignees_for_tasks` 用一次
  `WHERE task_id IN (...)` 取回全部任务的所有分配人，再在内存里按 task 分组。
- 因此列表端点恒为「1 条主查询 + 1 条关联查询」，**与行数无关**。
- **证据**（`tests/test_query_efficiency.py`）：3 行与 12 行的列表请求，SQL 条数**相同**；
  分配人查询恒为 1 条且包含 `IN (`。
- 为什么不用 `selectinload` / `joinedload`（§46 也允许）：两者抗 N+1 效果等价，但
  `selectinload` 的效果依赖「调用方没忘记 `.options(...)`」——漏写就**静默**退化成 N+1，
  没有任何报错。显式批量查询把「查几次」写死在代码里，可以直接被测试验证。
- 追问点：反过来，哪些地方**不该**批量？单条详情查询天然没有 N+1 问题，硬套批量只会
  让代码更难读。

---

## PostgreSQL

### 9. 为什么选择 PostgreSQL？

**一句话结论**：本项目需要的几项能力（部分索引、GIN、JSONB、trigram、CHECK 约束、
严格事务）在 PostgreSQL 上是原生且成熟的，而且**每一条都用上了**（不是选完就放着）。

- `ix_tasks_due_at_open`：**部分索引**，只索引未完成/未取消任务。
- `ix_operation_logs_payload`：**GIN(JSONB)**；`pg_trgm` + GIN 让 `ILIKE '%x%'` 走索引。
- 8 个**唯一约束**、3 个 **CHECK**（status / priority 枚举落库）——把完整性放在数据库，
  业务规则放在 Service，两者不互相替代。
- 事务 + 唯一约束组合，把并发注册这类竞态变成可处理的 409。
- **对比**：MySQL 没有部分索引；SQLite 并发写能力弱，用它做测试库会让「测试环境」与
  生产不同源——本项目测试**直连真实 PostgreSQL**（容器 5432 / 宿主 5433）。
- 代价：运维与调优比 SQLite 重得多（连接数、`max_connections` 与 Gunicorn worker 数
  的乘积关系，见 Q33）。

### 10. GIN 索引是什么？

**一句话结论**：GIN（Generalized Inverted Index）是**倒排索引**——key 是「值内部的元素」，
value 是「包含该元素的行」，专治「一个值里含多个元素」的列。

- 本项目三处：
  - `search_vector`（tsvector）：词 → 行；
  - `ix_tasks_title_trgm`：**trigram（字符三元组）→ 行**，让 `ILIKE '%x%'` 可用索引；
  - `ix_operation_logs_payload`：JSONB 的键值路径 → 行。
- 典型可命中的查询：`@>`（JSONB 包含）、`@@`（全文匹配）、`LIKE '%x%'`（trigram）。
- **不适合**范围比较（`>` / `BETWEEN`）——那是 B-tree 的领域；用错类型等于白建索引。
- 代价：写入更慢、索引更大（GIN 的 pending list 与 `fastupdate` 是相关调优参数）。

### 11. JSONB 有什么优势？

**一句话结论**：结构化与灵活性之间的折中——既能索引和查询，又不需要为每一种事件类型
加列。

- 本项目：`operation_logs.payload` 存审计上下文，如
  `{"old_status": "TODO", "new_status": "IN_PROGRESS"}`。不同 action 的字段结构不同，
  用 JSONB 就不必为每种 action 设计一套列或一张表。
- `operation_logs_archive.payload` 同构，因此归档可以直接整行搬（`INSERT ... ON
  CONFLICT DO NOTHING`），不需要做结构转换。
- **纪律（比优点更重要）**：JSONB 不是「不用设计 schema」的许可证。本项目所有**需要
  被筛选/排序的维度**（`resource_type`、`resource_id`、`user_id`、`created_at`）都是
  **独立列并带 B-tree 索引**；JSONB 只承载「不需要按列筛选的细节」。
- 与 `json` 类型的区别：JSONB 以二进制形式存储、去重键、不保留键顺序与空白，写入稍慢
  但可索引、查询快。

### 12. pg_trgm 用来做什么？

**一句话结论**：把字符串切成三字符片段（trigram）建 GIN 索引，从而让
`LIKE/ILIKE '%x%'` 这类**中缀匹配**也能走索引——而 B-tree 对 `%x%` 完全无能为力。

- 本项目：迁移 `6765bdcfa73e_add_task_search_indexes_and_search_vector.py` 建
  `CREATE EXTENSION pg_trgm` + `ix_tasks_title_trgm (title gin_trgm_ops)`。
- **实证**（`tests/test_task_search_indexes.py`）：关掉顺序扫描干扰后，
  `ILIKE '%login%'` 与 `ILIKE '%登录缺陷%'` 的执行计划都是
  `Bitmap Index Scan on ix_tasks_title_trgm`——改之前是顺序扫描。
- **为什么它比全文检索更适合本项目**：trigram 与**语言无关**。`to_tsvector('simple')`
  不做中文分词，实测 `'修复登录缺陷'` 会变成**一个** token，于是
  `to_tsquery('simple','登录')` 命中 0 条；而 trigram 对中文子串有效。这个边界被写成了
  **双向断言**，将来有人顺手把 `keyword` 改成全文检索会立刻变红。
- 代价：索引明显更大（每行 N 个 trigram），写入放大；短于 3 字符的查询退化（没有可用
  trigram）。

### 13. 什么情况下索引反而有害？

**一句话结论**：当**维护代价超过查询收益**时——索引不是「加了就快」。

- **低选择性**：如果 90% 的行都命中同一个值，走索引再回表比顺序扫描更慢。
- **冗余 / 重叠**：`(a)` 与 `(a, b)` 并存时前者通常多余；本项目刻意不为「看起来专业」
  堆索引，每个索引都能说出它服务哪条查询。
- **谓词不匹配**：为 `WHERE status = 'TODO'` 建的部分索引，在查询写成
  `WHERE status IN (...)` 时，如果规划器推不出谓词关系就用不上。
- **表太小**：规划器会选择顺序扫描——这其实是**正确**决定。
  ⚠️ 所以本项目做执行计划测试时**显式** `SET enable_seqscan = off` 来消除「表太小」的
  干扰。但要诚实：这只证明「索引可用」，**不能**据此声称任意数据规模下必然被选中。
- **写放大**：GIN / trigram 索引在大文本列上尤其明显，写多读少的表要谨慎。
- 纪律：`EXPLAIN` 说话，而不是直觉说话。

---

## Redis

### 14. Redis 为什么适合做限流？

**一句话结论**：限流是「高频、短生命周期、要求原子」的计数问题，正好落在内存数据库的
强项上。

- 本项目：`taskflow:ratelimit:{ip|user}:{标识}` 的 ZSET；窗口内计数 O(log N)；
  `PEXPIRE` 把 key 的 TTL 设为窗口长度，窗口静默后**自动回收**，不会无界增长。
- 对比方案：
  - 放 PostgreSQL：每次请求一次写 + 行级锁竞争，热路径成本高；
  - 放进程内存：多实例各算一份，等于把配额乘以实例数。
- **一个容易被忽略的细节**：限流**关闭**时本项目**完全不做 Redis 调用**（不是「调用了
  但忽略结果」）。有测试用「一调用就炸」的哨兵函数把这一点钉死，避免哪天变成「关了限流
  但每个请求仍多一次往返」。

### 15. ZSET 为什么适合滑动窗口？

**一句话结论**：它同时提供「按分数排序」和「按分数范围删除」，于是「窗口滑动」就是一次
范围删除。

- 本项目（`app/services/rate_limit.py`）：`score` = 请求毫秒时间戳，`member` = 本次请求
  唯一标识；`ZREMRANGEBYSCORE` 删窗口外 → `ZCARD` 数窗口内 → 判超限 → `ZADD` 记录 →
  `PEXPIRE` 续期。
- **为什么不用固定窗口**（`INCR` + `EXPIRE`）：限 60 次/分钟时，客户端可以在第 59 秒发
  60 次、第 61 秒再发 60 次——**两秒内 120 次全部放行**。滑动窗口按「每个请求的时间戳」
  判断「过去 N 秒有多少请求」，没有这个边界突刺。
- **前置条件（写进了函数文档）**：`member` 必须唯一。否则 `ZADD` 会更新已有成员的 score
  而不是新增，计数偏低、限流形同虚设。

### 16. Lua 为什么必要？

**一句话结论**：因为「读 → 判断 → 写」必须原子，否则并发下限流会被击穿。

- 具体失败模式：判定需要多步时，两个并发请求会交错——都读到「窗口内 59 次」→ 都判断
  「没超限」→ 都写入，实际放行 61 次。
- 本项目：五步（删窗口外 → 计数 → 判超限 → ZADD → PEXPIRE）全部在一个 Lua 脚本里，
  由 `EVAL` 执行；脚本在 Redis 中原子执行，判断与写入之间没有竞态窗口。
- 替代方案的代价：
  - `WATCH/MULTI` 是乐观锁，需要自己写重试循环，高并发下冲突重试本身是负担；
  - 只用 `INCR` 只能做固定窗口，语义直接退化（见 Q15）。
- 附带的一个正确性细节：时间取 `redis.call('TIME')`（**服务器时间**），不取客户端时间。
  多实例部署时客户端时钟不一致会让同一用户在不同实例落到不同窗口位置。

### 17. Redis 原子性怎么保证？

**一句话结论**：Redis 的命令是单线程执行的，而 Lua 脚本以**一个命令**的形式执行——
执行期间不会插入其它命令。

- **必须澄清的边界（面试高频追问）**：这不是数据库那种「失败可回滚」的事务。Lua 脚本
  若中途报错，**已经产生的写入不会自动回滚**。
- 所以本项目把脚本写成「先读后判、**只在放行时才写**」：被拒时不写 ZSET，错误路径不留
  副作用。
- 另一层原子性来自「单命令语义」：`ZREMRANGEBYSCORE`、`ZCARD`、`ZADD` 各自都是原子的，
  差别只在于**组合**起来是否原子——这正是需要 Lua 的原因。
- 追问方向：Redis Cluster 下同一脚本的所有 key 必须落在同一 slot（本项目限流的 key 单
  个 ZSET，天然满足）。

---

## JWT

### 18. Access Token 和 Refresh Token 为什么分开？

**一句话结论**：因为「无状态」与「可撤销」不可兼得，所以把它们分配给两个寿命不同的
凭据。

| | Access Token | Refresh Token |
| --- | --- | --- |
| 寿命 | 30 分钟 | 7 天 |
| 服务端状态 | 无（纯签名校验） | jti 落库（`refresh_tokens`） |
| 用途 | 每次请求携带 | 只用于换取新 Token 对 |

- 泄露 Access Token 的可利用窗口只有 30 分钟；**长期凭据的撤销能力放在数据库**，不放在
  每个请求的热路径上。
- **本项目的一条硬不变量**：登录时「签发 Refresh Token」与「登记 jti」必须在**同一事务**。
  否则会出现「客户端拿到 Token、服务端查不到 jti」的中间态——用户下一次刷新莫名 401。
- **诚实边界**：登出后 Access Token 在到期前仍然有效（最长 30 分钟）。要让它立刻失效
  需要 JWT 黑名单。本项目的黑名单 **key 约定已定义**（`taskflow:jwt:blacklist:<jti>`，
  TTL 必须不小于 Access Token 剩余寿命），但**校验链路未接入**——在没有需求驱动时改动
  认证热路径不划算（规则 §7）。这条边界写在 `app/core/redis_keys.py` 里，不假装已实现。

### 19. JWT 为什么需要 JTI？

**一句话结论**：无状态 Token 没有「个体身份」——要撤销或追踪**某一个** Token，必须有
一个能在服务端定位它的标识。

- 本项目：Refresh Token 带 `jti`，`refresh_tokens` 表上有 `UNIQUE(jti)`，撤销就是把这行
  置 `revoked=true`；刷新时校验链是「签名 → 过期 → `type` → **查库确认 jti 存在且未撤销**
  → 轮换」。
- 没有 jti 会怎样：
  - 只能存整个 Token 字符串来标记失效——更长、且签名算法或声明顺序变化就失效；
  - 无法区分同一用户签发的第 1 个和第 2 个 Refresh Token，也就无法实现轮换。
- **附带收益：轮换可检测重放**。旧 jti 在轮换时立即置撤销，若它再次出现，说明该 Token
  可能已被窃取，请求会被拒绝——这是「Refresh Token 轮换」这一实践的核心价值。

### 20. Logout 如何让 JWT 失效？

**一句话结论**：让长寿命的 Refresh Token 在服务端失效（撤销 jti），Access Token 依靠
短寿命自然过期。

- 本项目（`app/services/auth.py::logout_user`）：`POST /auth/logout` 把调用者自己的
  Refresh Token jti 置撤销，并保持**幂等**——签名错 / 过期 / 未登记 / 已撤销这些「Token
  本来就不可用」的情况也返回成功，不泄露「这个 Token 是否存在过」。
- 为什么不做 Access Token 黑名单：那会让**每个请求**多一次 Redis 查询，还要处理 TTL 与
  剩余寿命的匹配；本阶段没有需求驱动（见 Q18 边界）。
- 追问方向：如果业务真的要求「登出即刻踢掉所有设备」，设计就变了——需要「用户级
  token_version」或「按 user 维度的撤销时间戳」，比逐 jti 黑名单更省空间。

---

## RBAC

### 21. RBAC 怎么设计？

**一句话结论**：用户 → 角色 → 权限的间接层，让「谁有什么权限」与「权限集合如何演进」
解耦。

- 本项目五层链（4 张表 + users）：`users → user_roles → roles → role_permissions →
  permissions`。权限名是域化字符串（`task:create` / `task:read` / `task:update` /
  `task:delete` / `task:transition`、`attachment:download` 等），种子数据由迁移写入，
  因此**权限集合是可版本化的数据**，不是散落在代码里的常量。
- 两层落地：
  - **功能级**：路由上的依赖 `require_permission("task:read")`（AND 语义，可传多个）；
  - **资源级**：Service 内沿归属链校验（你是不是这个任务所属团队的成员）。
- **一个容易忽略但重要的设计**：`validate_permission_name()` 在权限名拼错时**立刻报错**。
  打错的权限名如果被当成「不需要权限」，就从笔误升级成了安全漏洞。
- 为什么不用「角色硬编码在代码里」：那样每加一个角色都要改代码并重新部署；RBAC 的
  数据化让「权限调整」变成数据变更（但代价是要控制谁能写这张表）。

### 22. Authentication 和 Authorization 有什么区别？

**一句话结论**：认证回答「你是谁」（401），授权回答「你能做什么」（403）；顺序不可颠倒，
语义不可混用。

- 本项目：
  - `get_current_user` 只做「HTTP 凭证 → 已认证用户」的翻译，失败一律 **401**（并带
    `WWW-Authenticate: Bearer`）；
  - 认证通过后由 `require_permission` 追加判定，缺权限 **403**，文案列出缺失的权限名；
  - 「凭证有效但账号被禁用」属于第三种情况——本项目按 **403** 处理（认证过了，但不能用）。
- **为什么在意状态码**：401 告诉客户端「去重新登录」，403 告诉它「登录了也不行」。混用会
  让客户端做出错误动作（例如拿 403 去清 Token，造成登录死循环）。
- 追问方向：`WWW-Authenticate` 头不是装饰——它是 HTTP 规范里 401 的组成部分，客户端库
  会据此决定是否刷新 Token。

### 23. 如何防止越权？

**一句话结论**：两层校验——功能级权限 + 资源级归属链；并且**用 404 而不是 403 来隐藏
资源是否存在**。

- 本项目：
  - 资源级校验沿 `team_members` 归属链（任务 → 项目 → 团队）；
  - 跨团队或不存在**统一 404 + 同文案**（`Task not found` / `Project not found` /
    `User not found`），避免攻击者用状态码差异枚举「哪些 id 真实存在」；
  - 只有「已在归属链上但缺具体权限」才给 403（并明示文案）。
- 其他越权面与对应防线：
  - **IDOR / 路径穿越**（附件）：下载有独立权限 + 归属链；存储键有 `validate_key`（语义层，
    拒绝 `..`、绝对路径、URL 编码变体）与 `LocalStorageBackend._resolve`（结构层，解析后的
    真实路径必须仍在根目录内）双层守卫；
  - **垂直越权**（低权限做高权限操作）：删除任务要求团队角色 OWNER/ADMIN，而不是「是成员
    就行」；分配/流转是协作式（成员即可），这个差异是刻意的；
  - **上传漏洞**：大小边读边计数（不信任 `Content-Length`）、类型白名单、服务端生成存储键。
- 证据：`tests/test_team_project_permissions.py`、`tests/test_attachment_security.py`、
  `tests/test_storage_guards.py`（42 项）、`tests/test_permission_dependency.py`。

---

## Celery

### 24. 为什么需要 Celery？

**一句话结论**：把「不该拖住请求、并且需要重试与持久化」的工作移出请求生命周期。

- 本项目三类任务：站内通知派发（一次任务创建/流转可能产生多条）、操作日志归档、过期附件
  清理。
- 收益：请求路径变短；Worker 崩溃消息不丢（`acks_late` + `reject_on_worker_lost`）；可重试、
  可限时、可独立扩容（Worker 与 API 是**同一镜像、不同命令**）。
- **代价必须说清**：引入 Celery 也就引入了「投递语义」（at-least-once）和「幂等」这两个
  必须自己解决的问题（见 Q26 / Q27）。如果业务只需要「记一条日志」，用
  `BackgroundTasks` 就够——不要为了架构好看而上队列。
- 一个刻意的接线细节：Celery 在 Redis 里的键统一挂 `global_keyprefix="taskflow:"`，因此
  `taskflow:*` 之外都不是本项目的键，运维排查和按前缀清理都干净。

### 25. Celery 和 FastAPI BackgroundTasks 有什么区别？

**一句话结论**：`BackgroundTasks` 是**同进程内**「响应返回后继续跑」；Celery 是**独立
进程/机器上的队列消费**。

| 维度 | `BackgroundTasks` | Celery |
| --- | --- | --- |
| 执行位置 | 与 API 同进程 | 独立 Worker 进程/机器 |
| 进程崩溃/重启 | 任务丢失 | 消息保留，可重投（at-least-once） |
| 重试 / 退避 | 无内建 | `autoretry_for` + `retry_backoff` + jitter |
| 超时控制 | 无 | `soft_time_limit` / `time_limit` 双保险 |
| 水平扩展 | 随 API 一起扩 | Worker 独立扩容 |
| 观测 | 无 | 结果后端、`STARTED` 状态、任务名 |

- 本项目选 Celery 的判据是**「不能丢」和「要重试」**：通知漏发是产品可见故障，归档与
  清理是运维任务，都需要重试与可观测。
- 什么时候 `BackgroundTasks` 就够了：不重要、可丢、不重试的副作用（比如顺手上报一条
  统计）。本项目通知没有走这条路，正是因为「通知丢了用户会问」。

### 26. Celery 任务失败怎么办？

**一句话结论**：靠「投递语义 + 重试策略 + 幂等」三者配合，而不是靠「任务不会失败」的假设。

- **投递语义**（`app/tasks/celery_app.py`）：
  - `task_acks_late=True`——执行完成才 ack，Worker 崩溃消息不丢；
  - `task_reject_on_worker_lost=True`——Worker 被 SIGKILL/OOM 时消息重新入队；
  - `worker_prefetch_multiplier=1`——长任务不会囤积在单个进程上饿死其它消息。
  这三条合起来意味着投递是 **at-least-once：任务可能被重复执行**。
- **重试**：`autoretry_for=(SQLAlchemyError, OSError)` + `retry_backoff`（指数退避）+
  `max_retries` + **jitter**（抖动，避免一批任务同时重试形成二次雪崩）。
- **超时**：`soft_time_limit` 抛 `SoftTimeLimitExceeded`（任务可自行清理），`time_limit`
  硬杀进程兜底。
- **安全**：`accept_content=["json"]` 禁掉默认的 pickle——反序列化即执行任意代码，任务消息
  一旦被拿到就是 RCE。
- **诚实边界**：超过 `max_retries` 之后本项目**没有接入告警或死信队列**，需要人工介入。
  这是已知的运维缺口，生产化的下一步应该补上。

### 27. 如何保证任务幂等？

**一句话结论**：幂等不能靠 Celery，必须由**每个任务自己**实现；思路是「让重复执行不产生
额外副作用」。

- 本项目三种做法：
  1. **幂等键**（通知派发）：调用方传入 `idempotency_key`，任务先查是否已存在，存在则直接
     返回、不重复落库。测试里用哨兵区分「未传」与「传了 `None`」——这个区分本身修过一个
     **假绿测试**（自动生成分支从未被执行）。
  2. **`ON CONFLICT DO NOTHING`**（日志归档）：归档行复用原日志 id，重复投递时被跳过；
     且「插归档 + 删主表」在**同一事务**里——崩溃重投时要么重搬（上次回滚），要么 no-op
     （上次已提交），既不丢日志也不重复。
  3. **可重复执行**（附件清理）：只删「数据库中已无引用」的孤儿文件，且删文件操作本身幂等。
- 为什么必须如此：at-least-once 是**设计前提**（规则 §8：不要假设 Celery 任务只执行一次），
  不是异常情况。把幂等当成「失败时的补救」就会写出重复通知、重复归档。

---

## 数据库

### 28. 为什么需要事务？

**一句话结论**：因为业务动作常常由多个数据库写组成，而「部分成功」在业务上就是坏数据。

- 本项目实例：
  - **创建任务** = `INSERT tasks` + `INSERT operation_logs`，同一事务——业务回滚则审计
    不落库（不会留下「日志说创建了、但任务不存在」的记录）；
  - **状态流转** = 改 `status` + 写审计，同一事务；
  - **日志归档** = 插归档表 + 删主表，同一事务（崩溃重投语义见 Q27）。
- **边界纪律**：事务边界在 **Service**，不在 Router、不在 CRUD。CRUD 只 `flush()` 不
  `commit()`——否则「多个动作一个事务」根本不成立（每个 CRUD 各自提交，就是把一个业务动作
  拆成多个事务）。
- 另一条不变量：**签发 Token 与登记 jti 同事务**（Q18），否则会出现服务端查不到的凭据。

### 29. 什么情况下会出现脏数据？

**一句话结论**：缺少约束、缺少事务，或者把「读—判断—写」误当成原子操作。

| 场景 | 本项目如何防 | 真实教训 |
| --- | --- | --- |
| 部分写入 | Service 级事务 + 同事务审计 | — |
| 竞态唯一冲突 | 数据库 `UNIQUE` 兜底 + `IntegrityError` → 409 | **修过一个真实缺陷**：`IntegrityError` 兜底只包住了 `commit()`，而冲突实际由内部的 `flush()` 抛出，导致兜底分支不可达——真实并发注册返回 500 而不是 409 |
| 丢失更新 | 见 Q30（**部分未防住，已登记**） | — |
| 无约束的枚举 | 库层 CHECK（`ck_tasks_status_values`、`ck_tasks_priority_values`）兜底 | 只在应用层校验时，任何旁路写入都能造出非法状态 |
| 孤儿数据 | 外键 + 按语义选择 CASCADE / RESTRICT | `operation_logs.user_id` **有意不加外键**，否则删用户会销毁审计痕迹 |
| 测试污染 | 每个测试文件自带 `RUN_TOKEN` 前缀 + 精确 teardown | 曾因 3 个测试文件漏清 `operation_logs`，在开发库留下 **507 行**孤儿审计日志 |

- 一句总结：**数据库负责完整性，Service 负责业务规则**。把完整性寄托在应用层，等于假设
  所有写入路径都经过你的 Service。

### 30. 如何处理并发更新？

**一句话结论**：先分类——「最后写入者获胜是否可接受」「是否必须串行化」，再选手段；不要
一上来就说「加乐观锁」。

- 本项目**已经**用的手段：
  - 数据库唯一约束 + `IntegrityError` → 409（并发注册、重复分配）；
  - 单事务 + `ON CONFLICT DO NOTHING`（日志归档的重复投递）；
  - 幂等键（通知派发重投）；
  - Redis 侧「读—判断—写」用 **Lua 单命令**原子化（限流，见 Q16/Q17）。
- **已知残余风险（诚实记录）**：任务**状态流转**是「读当前状态 → 校验 → 写」，
  **没有加行锁**（全仓库没有 `SELECT ... FOR UPDATE`）。两个并发的 transition 请求理论上
  都可能读到旧状态并通过校验，从而让其中一次校验事实上失效（丢失更新），审计记录也会与
  最终状态不一致。
- 修复方向是明确的（三种，按侵入性排序）：
  1. **条件更新**（乐观锁）：`UPDATE tasks SET status = :new WHERE id = :id AND status =
     :old`，检查受影响行数，为 0 说明状态已被别人改过 → 409；
  2. `SELECT ... FOR UPDATE` 锁住该行再校验（悲观锁，写少读多更合适）；
  3. 加 `version` 列做通用乐观锁。
- **为什么现在没做**：同一任务被并发流转的概率在本项目规模下极低，而它属于**代码改动**
  而非文档工作；已登记为遗留项（`docs/TASKS.md`）与已记录偏差（`docs/QUALITY.md` D9）。
  面试上讲这一条的价值在于：能说清缺口、影响、修复方案**以及不修的理由**。

---

## 工程化

### 31. Docker 为什么使用？

**一句话结论**：把「运行时环境」变成可复现的产物，并用镜像分层与进程隔离获得部署一致性。

- 本项目 `Dockerfile`：
  - 基础镜像 `python:3.13-slim`，与 CI 的 `PYTHON_VERSION` 一致——避免 CI 与生产是两个
    大版本；
  - **先 `COPY requirements.txt` 再装依赖，最后才拷代码**（利用层缓存：改代码不必重装
    依赖）；
  - 以非 root 的 `appuser` 运行；构建时创建并授权 `/app/storage`（否则上传会 EACCES）；
  - 生产镜像只装 `requirements.txt`——lint / 覆盖率工具留在 `requirements-dev.txt`，
    不把约 10MB 的死重量塞进生产镜像。
- 两个 compose：
  - 开发栈发布 `8000 / 5433 / 6389`，便于本机直连调试；
  - **生产栈只有 Nginx 发布端口**，PostgreSQL / Redis / app 都不出现在宿主网络上；密钥用
    `$VAR:?` 必填语法 **fail-fast**（缺失或沿用开发默认值直接拒绝启动）。
- 追问方向：为什么不用 `docker-compose` 挂载源码热重载跑生产？因为它会把「镜像即产物」
  这个性质毁掉。

### 32. Nginx 在项目中做什么？

**一句话结论**：生产环境的**唯一入口**——反向代理 + 粗粒度防护 + 真实客户端 IP 的信任
边界。

- §31 要求五件事的落地（`nginx/nginx.conf`）：
  1. **反向代理**：`upstream app_backend { server app:8000; }` + `location /`，并配
     `keepalive`（`Connection` 必须置空，否则退化成短连接）；
  2. **请求体上限**：`client_max_body_size 12m`，**刻意大于应用侧的 10 MiB**——如果 Nginx
     更严格，超限上传会拿到 Nginx 的 HTML 错误页而不是 API 的统一 JSON 信封，客户端无法
     统一处理；同时避免两处配置漂移；
  3. **超时**：connect 短（快速失败）、read/send 给足（与 Gunicorn `--timeout` 同量级）；
  4. **安全头**：`X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy`，用
     `always` 让 4xx/5xx 也带上；`server_tokens off` 不暴露版本号；
  5. **静态附件访问**：**有意不实现**——直出会完全绕过鉴权（知道路径即可下载任意私有
     附件，教科书式 IDOR）。要优化吞吐，正确方向是 `X-Accel-Redirect` 指向 `internal`
     location，让鉴权留在应用层。
- **最关键的一条**：用 `$remote_addr` **覆盖式**写入 `X-Forwarded-For`，而不是
  `$proxy_add_x_forwarded_for` 的拼接语义——后者的「客户端 IP」由客户端自己决定。
- 细节：`location = /nginx-health` 是代理自身的存活探针，**不探上游**（否则应用重启时
  Nginx 也被标记不健康，「入口挂了」与「后端重启中」两件事就混在一起）；日志里
  `rid=$http_x_request_id` 让 Nginx 与应用两侧的日志能用同一个 id 串起来。

### 33. Gunicorn 和 Uvicorn 的关系？

**一句话结论**：Gunicorn 提供**进程管理**，Uvicorn 提供 **ASGI 协议实现**，
`UvicornWorker` 把两者接起来。

- 本项目：生产 `gunicorn app.main:app --worker-class=uvicorn.workers.UvicornWorker
  --workers=${WEB_CONCURRENCY:-2}`；开发直接 `uvicorn app.main:app`。
- 为什么不用「Uvicorn 多进程」（`--workers`）：Gunicorn 的进程管理更成熟——worker 超时、
  优雅重启、信号处理、按需扩缩；Uvicorn 自带的 `--workers` 只是薄壳。
- **参数纪律（容易被忽略的真实约束）**：worker 数不是越大越好。每个 worker 有自己的连接
  池，`workers × pool_size` 不能超过 PostgreSQL 的 `max_connections`；本项目
  `WEB_CONCURRENCY` 默认 2 并允许按内存与下游连接数调整。
- 追问方向：`UvicornWorker` 下每个 worker 是独立事件循环，因此**进程内状态**（内存缓存、
  本地锁）不能跨 worker 共享——这也是本项目把限流放 Redis、把共享状态放数据库的原因之一。

### 34. GitHub Actions 做什么？

**一句话结论**：把「合并前必须成立的性质」变成机器执行的检查，让「我本地是好的」不再
有意义。

- 本项目三 job（`.github/workflows/ci.yml`）：
  - `lint`：Python 3.13 + `ruff check .`（ruff 版本与规则集**钉死在仓库**）；
  - `test`：`postgres:16` / `redis:7` service → **迁移可逆性三步** → 全量 `pytest`；
  - `docker-build`：`docker build --tag taskflow-app:ci .`（只验证可构建，**不推送镜像**）。
- 设计细节：service 端口映射成测试里硬编码的 `5433` / `6389`；显式注入 `DATABASE_URL` /
  `REDIS_URL` / `JWT_SECRET_KEY`（默认值是容器内服务名，CI 里既无 `.env` 也无 Docker
  网络）；`permissions: contents: read` 最小权限；同分支的新 run 取消旧 run。
- **为什么 CI 配置自己也有测试**：`tests/test_ci_workflow.py`（35 项）断言 ci.yml 里这些
  性质——端口、注入的变量、迁移三步、无写权限。否则有人改坏 CI 时，唯一的反馈是「CI 不
  跑了」或「跑得没意义」，而不是一条失败的测试。

### 35. 如何设计 CI？

**一句话结论**：按「失败得越早越便宜」排序，每个 job 只承担一个明确的失败语义，并且让
**CI 跑的东西与本地跑的东西尽可能一致**。

- 本项目的取舍：
  - **分 job 而非一条龙**：lint 快速反馈（限 10 分钟）；test 重但涵盖迁移可逆性与全量
    测试（限 30 分钟）；docker-build 独立验证镜像可构建。三者并行，失败点一目了然。
  - **不推送镜像**：推送需要 `packages:write` 与 registry 凭据，把权限面扩到一个纯验证
    步骤上不划算；仓库目前也没有镜像发布需求。
  - **覆盖率不进 CI 门禁**：覆盖率是诊断指标、不是质量目标；设阈值会诱导「为了抬数字写
    无意义断言」。本项目只在本地测量并写入 `docs/QUALITY.md`（决策记录在案）。
  - **迁移可逆性必须用 `set -euo pipefail` 串在同一 shell**：否则会出现「downgrade 悄悄
    失败 → 后面的 upgrade 变成 no-op → pytest 在旧库上通过」这种**假绿**。
  - **依赖版本全固定**（`requirements*.txt` 全部 `==`、ruff 版本钉死）→ 「CI 是否通过」只
    取决于提交内容，与「CI 当天装到哪个版本」无关。
- 一条容易被忽略的判据：**CI 里应该跑那些「人容易忘记、但忘记代价很大」的检查**。本项目
  除了 lint / test，还把「文档一致性」（`scripts/check_docs.py` 的逻辑）跑进了 pytest——
  因为进度文档「报成功但没落盘」这类问题不报错、不影响任何测试，唯一的表现是文档说谎
  （曾发生 4 次）。

---

## 延伸：几个能撑满 10 分钟的深水区

如果面试官想继续深挖，下面每一条都有完整的「问题 → 权衡 → 决策 → 证据」链路：

| 话题 | 一句话钩子 | 具体位置 |
| --- | --- | --- |
| 反代后的真实客户端 IP | `X-Forwarded-For` 是客户端可控输入，采信它就等于把限流配额交给攻击者 | `nginx.conf` 覆盖式写入 + `app/core/client_ip.py` 双条件判定（DECISIONS 018/040） |
| 中文搜索为什么不用全文检索 | `to_tsvector('simple')` 不做中文分词，切过去会让子串搜索**静默失效** | DECISIONS 045 + `tests/test_task_search_indexes.py` 双向断言 |
| 私有附件与 Nginx 直出的冲突 | 静态直出 = 绕过鉴权 = IDOR；正确优化方向是 `X-Accel-Redirect` | `nginx.conf` 注释 + DECISIONS 040 |
| 日志脱敏的漏洞面 | 只处理字符串消息的过滤器，会被 `logger.info({"password": ...})` 绕过（dict repr 明文落盘） | `app/core/logging_config.py` + `tests/test_logging.py`（QUALITY F2） |
| 限流关闭时是否仍访问 Redis | 「关闭」应当是**零**额外往返，而不是「调用了但忽略结果」 | `tests/test_quality_gaps.py` 用「一调用就炸」的哨兵钉死 |
| 文档也会说谎 | 进度回写「报成功但没落盘」，不报错、不影响测试，五次里两次靠人发现 | `scripts/check_docs.py` + 反向用例（QUALITY D8） |
| 覆盖率数字的口径 | 「99.96%」依赖于 `exclude_also` 配置，不披露就是误导 | `docs/QUALITY.md` 第 1.2 节双口径披露 |
