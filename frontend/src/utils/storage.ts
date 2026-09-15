/**
 * 本地凭证存储。
 *
 * 为什么令牌的持久化单独放在这里，而不是直接写在 Pinia store 里：
 *
 *   `stores/auth.ts` → `api/auth.ts` → `utils/request.ts`
 *
 * 请求层需要读令牌（加 `Authorization` 头），如果它反过来 import store 就会形成
 * 循环依赖。把「令牌存在哪」抽成本模块后，请求层只依赖它，store 只负责「谁是
 * 当前用户」——两边都只依赖一个无依赖的底层模块。
 *
 * 关于存储介质：规格 §10 只要求客户端保存 Token，没有指定 localStorage。这里选
 * localStorage 是因为刷新页面后必须保持登录；代价是 XSS 可以读到令牌。后端
 * 没有 cookie/session 机制（`RefreshRequest` 走请求体），所以这里没有更安全的
 * 可选方案，只能靠「不引入不可信脚本」的常规防线（见 docs/DECISIONS.md 047）。
 */

import type { TokenPair } from '@/types/auth'

/** 加前缀避免与同域下其它应用的键冲突。 */
const ACCESS_TOKEN_KEY = 'taskflow:access_token'
const REFRESH_TOKEN_KEY = 'taskflow:refresh_token'

/**
 * 包一层 try/catch：Safari 隐私模式、存储配额耗尽、以及测试环境里被替换过的
 * `localStorage` 都会直接抛异常。凭证读写失败不应该让页面白屏——退化为
 * 「本次会话不持久化」即可。
 */
function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    /* 见上：存储不可用时不阻断业务 */
  }
}

function remove(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    /* 见上 */
  }
}

export const tokenStorage = {
  getAccessToken(): string | null {
    return read(ACCESS_TOKEN_KEY)
  },

  getRefreshToken(): string | null {
    return read(REFRESH_TOKEN_KEY)
  },

  /** 保存一对令牌（登录成功或刷新成功后调用）。 */
  save(pair: TokenPair): void {
    write(ACCESS_TOKEN_KEY, pair.access_token)
    write(REFRESH_TOKEN_KEY, pair.refresh_token)
  },

  /** 清除全部本地凭证（登出、刷新失败、账号被禁用）。 */
  clear(): void {
    remove(ACCESS_TOKEN_KEY)
    remove(REFRESH_TOKEN_KEY)
  },
}
