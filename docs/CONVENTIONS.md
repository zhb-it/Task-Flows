# Coding Conventions

- Python 遵循 PEP 8。
- 使用 Type Hint。
- FastAPI 路由保持薄，业务逻辑进入 Service。
- 数据库访问进入 CRUD。
- SQLAlchemy Session 生命周期由统一依赖管理。
- 环境变量进入 `.env`，仓库只提交 `.env.example`。
- 密码、Token、Secret 不进入日志。
- 数据库结构变化只能通过 Alembic。
- 异常使用统一业务异常体系。
- 查询关注分页、索引、N+1。
- Git Commit 推荐 Conventional Commits：feat/fix/test/docs/refactor。
- 不为了“高级”而增加无实际用途的依赖。
