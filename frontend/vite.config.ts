import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

/**
 * Vite 配置（前端规格 §55「开发环境代理」）。
 *
 * 开发时的链路是：
 *
 *     浏览器 → Vite Dev Server(5173) → /api → FastAPI(8000)
 *
 * 代理不是「可选优化」而是**必需项**：后端 `app/main.py` 没有注册任何
 * `CORSMiddleware`，浏览器直连 8000 会被同源策略拦下。走代理后请求对浏览器
 * 而言是同源的，因此不需要 CORS。详见 docs/DECISIONS.md 047。
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    build: {
      // 演示项目保留 sourcemap 便于排查；生产若要关掉，改这里即可。
      sourcemap: mode !== 'production',
      // Element Plus 全量引入后单个 chunk 会超过默认 500 kB 警告线（见 README
      // 「已知取舍」），这里放宽阈值避免每次构建都刷警告。
      chunkSizeWarningLimit: 1500,
    },
  }
})
