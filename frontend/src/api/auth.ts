/**
 * 认证 API（前端规格 §38：页面只调用 `authApi.xxx()`）。
 *
 * 端点与请求/响应结构逐一对齐 `docs/API_CONTRACT.md` 与 `app/api/v1/auth.py`：
 *
 * | 函数                | 端点                        | 成功状态 |
 * | ------------------ | --------------------------- | -------- |
 * | `register`         | `POST /auth/register`       | 201      |
 * | `login`            | `POST /auth/login`          | 200      |
 * | `logout`           | `POST /auth/logout`         | 200      |
 * | `fetchCurrentUser` | `GET  /users/me`            | 200      |
 *
 * ⚠ 两处与规格文档的偏差（已记录在 docs/FRONTEND_API_MAPPING.md）：
 *
 * 1. 规格 §58 的映射表写「当前用户 → `/auth/me`」，**真实端点是 `/users/me`**
 *    （`app/api/v1/users.py`，router prefix 是 `/users`）。按规格 §57
 *    「以实际后端契约为准」，这里用 `/users/me`。
 * 2. `POST /auth/logout` **需要认证头**并且请求体带 `refresh_token`
 *    （`LogoutRequest`）。它不是「无凭证也能调用」的端点，所以调用方必须先
 *    保证本地还有 Access Token——见 `stores/auth.ts::logout`。
 *
 * 刷新令牌的请求不走这里：它是请求拦截器的内部行为（`utils/request.ts`）。
 */

import { http } from '@/utils/request'
import type { LoginRequest, RegisterRequest, TokenPair } from '@/types/auth'
import type { User } from '@/types/user'

/** `POST /auth/register` —— 注册成功返回 201 与新建用户。 */
function register(payload: RegisterRequest): Promise<User> {
  return http.post<User>('/auth/register', payload)
}

/** `POST /auth/login` —— 返回 Access / Refresh 令牌对。 */
function login(payload: LoginRequest): Promise<TokenPair> {
  return http.post<TokenPair>('/auth/login', payload)
}

/**
 * `POST /auth/logout` —— 撤销当前用户的 Refresh Token。
 *
 * 后端是幂等语义：Token 本来就不可用时静默成功。因此调用方可以无条件清理本地
 * 凭证（见 store 实现）。
 */
function logout(refreshToken: string): Promise<null> {
  return http.post<null>('/auth/logout', { refresh_token: refreshToken })
}

/** `GET /users/me` —— 当前 Access Token 所属用户。 */
function fetchCurrentUser(): Promise<User> {
  return http.get<User>('/users/me')
}

export const authApi = { register, login, logout, fetchCurrentUser }
