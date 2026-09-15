/// <reference types="vite/client" />

/**
 * 前端可用的环境变量。
 *
 * 规格 §54 明令：数据库密码 / JWT Secret / Redis 密码 一律不得放进前端环境变量。
 * 原因是 Vite 会把 `VITE_*` 的值**内联进打包产物**，浏览器里能直接看到。
 * 因此这里的类型声明只允许「非敏感的公开配置」。
 */
interface ImportMetaEnv {
  /** 站点标题（浏览器标签页 / 侧边栏 Logo 文案）。 */
  readonly VITE_APP_TITLE: string
  /** API 基地址。**必须**是相对路径 `/api/v1`，见 .env.development 的说明。 */
  readonly VITE_API_BASE_URL: string
  /** 仅开发环境使用：Vite 代理的目标地址。 */
  readonly VITE_API_PROXY_TARGET?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
