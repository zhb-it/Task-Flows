import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

/**
 * ESLint 扁平配置（前端规格 §2 / §75）。
 *
 * 顺序有讲究：JS 基础 → TS 规则 → Vue 规则 → Vue 里的 TS 解析器 → 项目自定义
 * 规则 → prettier（**必须放最后**，它的作用是关掉所有与格式化冲突的规则）。
 */
export default tseslint.config(
  {
    name: 'taskflow/ignores',
    ignores: ['dist/**', 'node_modules/**', 'coverage/**', 'public/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'taskflow/vue-uses-ts-parser',
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    name: 'taskflow/rules',
    rules: {
      // 规格 §4 把视图文件定名为 Login.vue / Register.vue / Dashboard.vue / Profile.vue，
      // 这些是单词组件名，按 Vue 官方风格指南会被判违规——此处按规格放行。
      'vue/multi-word-component-names': 'off',
      // 允许 error/warn 打点；普通 console.log 只警告，提醒别把调试语句提交上来。
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // 规格 §39 明令禁止无理由 any。
      '@typescript-eslint/no-explicit-any': 'error',
    },
  },
  prettier,
)
