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

## 完成条件
测试失败不能标记任务完成；不能虚构测试结果。
