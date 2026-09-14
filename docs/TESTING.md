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

## 完成条件
测试失败不能标记任务完成；不能虚构测试结果。
