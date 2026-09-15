import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

/**
 * 单元测试配置（前端规格 §2 / §71）。
 *
 * 与 `vite.config.ts` 分开，是为了让构建配置不依赖测试工具——`vite build`
 * 不应该因为「vitest 没装」而失败。
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['tests/unit/**/*.spec.ts'],
    // 每个用例前还原被 spy/mock 的函数，避免用例之间互相污染。
    restoreMocks: true,
  },
})
