/**
 * 认证相关类型（前端规格 §39）。
 *
 * 对齐 `app/schemas/auth.py`：
 * - `LoginRequest{username, password}`
 * - `RefreshRequest{refresh_token}` / `LogoutRequest{refresh_token}`
 * - `TokenResponse{access_token, refresh_token, token_type}`
 *
 * 注意字段是 **snake_case**：后端直接返回 Pydantic 模型，没有做命名风格转换，
 * 前端这里保持原样，避免在请求层做无意义的映射（映射一旦漏字段就是静默 bug）。
 */

import type { User } from '@/types/user'

/** 注册请求体，对齐 `app/schemas/user.py::UserCreate`。 */
export interface RegisterRequest {
  username: string
  email: string
  password: string
}

/** 登录请求体，对齐 `app/schemas/auth.py::LoginRequest`。 */
export interface LoginRequest {
  username: string
  password: string
}

/** 登录与刷新共用的 Token 对，对齐 `TokenResponse`。 */
export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 注册成功后返回的用户资料（`201 Created`）。 */
export type RegisteredUser = User
