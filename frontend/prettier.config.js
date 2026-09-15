/**
 * Prettier 配置（前端规格 §2）。
 *
 * 与 ESLint 的分工：ESLint 管「代码对不对」，Prettier 管「长什么样」。
 * 两者冲突的规则由 `eslint-config-prettier` 在 eslint.config.js 末尾关掉。
 */
export default {
  semi: false,
  singleQuote: true,
  printWidth: 100,
  tabWidth: 2,
  trailingComma: 'all',
  arrowParens: 'always',
  endOfLine: 'lf',
  htmlWhitespaceSensitivity: 'ignore',
}
