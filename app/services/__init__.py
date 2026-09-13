"""Service layer.

Services own business logic, permissions, state machines and transaction
coordination (项目规则 §4 / ARCHITECTURE.md：事务边界由 Service 统一协调).
Routers stay thin and CRUD stays free of auth concerns.
"""
