/**
 * 设计令牌护栏（TASK-130）。
 *
 * 为什么需要这个文件：CSS 自定义属性**引用未定义的变量不会报错**——整条声明
 * 在计算值阶段被判为无效，属性退回初始值/继承值，页面只是「看起来有点怪」。
 * typecheck / lint / build 三个门禁全都发现不了它。这不是假想的风险：命令面板
 * 与顶栏曾经引用一整套从未定义的 `--tf-border` / `--tf-bg` / `--tf-shadow-lg`
 * 等变量，结果命令面板成了「透明底、方角、无阴影」的浮层，遮罩也完全不生效
 * （`color-mix(..., var(--tf-overlay) ...)` 整条失效），而四门全绿。
 *
 * 三条不变量：
 *
 * 1. **引用必须已定义**：源码里 `var(--x)` 的每个 `--x` 都要能在我们自己的
 *    CSS / `<style>` 里找到定义（`--el-*` 除外——那是 Element Plus 运行时提供的）。
 * 2. **双主题对等**：主题相关的令牌必须在 `:root` 与 `html.dark` 两块里都定义，
 *    不允许「只在明色定义、暗色忘掉」——那正是暗色下文字看不见的常见成因。
 * 3. **不写魔法颜色**：组件/页面样式里不出现十六进制颜色或 `rgb()/rgba()/hsl()`，
 *    颜色一律走令牌（`tokens.css` 自身是令牌来源，豁免）。
 */

import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

import { describe, expect, it } from 'vitest'

/**
 * 用 `process.cwd()` 定位源码：vitest 的 root 是 `frontend/`（配置文件所在目录），
 * 而 `import.meta.url` 在 jsdom 环境下不是 `file:` 协议，`fileURLToPath` 会抛错。
 */
const SRC_DIR = join(process.cwd(), 'src')
const TOKENS_FILE = join(SRC_DIR, 'assets', 'styles', 'tokens.css')

/** 递归收集 `src` 下的样式来源文件。 */
function collectFiles(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      collectFiles(full, out)
      continue
    }
    if (/\.(vue|css|ts)$/.test(entry)) {
      out.push(full)
    }
  }
  return out
}

const FILES = collectFiles(SRC_DIR)

/** 文件里所有 `<style>` 块（.vue）或整个文件（.css）的 CSS 文本；.ts 返回空。 */
function cssOf(file: string): string {
  if (file.endsWith('.ts')) {
    // TS 里没有样式定义（注释里出现 `--x:` 不算定义，否则护栏会被注释「喂饱」）
    return ''
  }
  const text = readFileSync(file, 'utf8')
  if (!file.endsWith('.vue')) {
    return text
  }
  const blocks = text.match(/<style[^>]*>[\s\S]*?<\/style>/g) ?? []
  return blocks.join('\n')
}

function read(file: string): string {
  return readFileSync(file, 'utf8')
}

/** 去掉 CSS 注释与 HTML 注释，避免「注释里举例写了 #fff / var(--x)」被误判。 */
function stripComments(css: string): string {
  return css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '')
}

const CSS_TEXTS = FILES.map((f) => ({ file: f, css: cssOf(f) }))

/** 我们自己定义过的自定义属性。 */
const DEFINED = new Set<string>()
for (const { css } of CSS_TEXTS) {
  for (const m of css.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)) {
    DEFINED.add(m[1])
  }
}

describe('设计令牌：引用必须已定义', () => {
  it('源码中不存在未定义的 var(--x)（--el-* 由 Element Plus 运行时提供，豁免）', () => {
    const missing: string[] = []

    for (const file of FILES) {
      const text = stripComments(read(file))
      for (const m of text.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)) {
        const name = m[1]
        if (name.startsWith('--el-')) continue
        if (DEFINED.has(name)) continue
        if (name.startsWith('--vite') || name.startsWith('--vue')) continue
        missing.push(`${relative(SRC_DIR, file)}: ${name}`)
      }
    }

    expect(missing, `未定义的设计令牌：\n${missing.join('\n')}`).toEqual([])
  })

  it('令牌文件本身就是定义来源（防空转：改了扫描逻辑导致上面恒过）', () => {
    const tokensCss = read(TOKENS_FILE)

    expect(tokensCss).toMatch(/--brand-600\s*:/)
    expect(DEFINED.has('--brand-600')).toBe(true)
    expect(DEFINED.size).toBeGreaterThan(30)
  })
})

describe('设计令牌：双主题对等', () => {
  /**
   * 主题相关令牌（颜色面/边框/文字/阴影/遮罩/认证底色）。
   * 显式列举而不是用正则猜：清单本身就是「哪些令牌必须成对出现」的文档。
   */
  const THEME_DEPENDENT = [
    '--bg-page',
    '--bg-surface',
    '--bg-surface-2',
    '--bg-inverse',
    '--bg-auth',
    '--overlay-backdrop',
    '--border-color',
    '--border-strong',
    '--text-primary',
    '--text-secondary',
    '--text-tertiary',
    '--shadow-sm',
    '--shadow-md',
    '--shadow-lg',
    '--shadow-brand',
  ]

  /** 从 CSS 里取出某个选择器块的内容。 */
  function blockOf(selector: string): string | null {
    const css = read(TOKENS_FILE)
    const index = css.indexOf(`${selector} {`)
    if (index < 0) return null
    return css.slice(index, css.indexOf('}', index))
  }

  it('tokens.css 同时声明了 :root 与 html.dark', () => {
    expect(blockOf(':root')).not.toBeNull()
    expect(blockOf('html.dark')).not.toBeNull()
  })

  it.each(THEME_DEPENDENT)('%s 在明暗两个主题块里都定义了', (token) => {
    const light = blockOf(':root') ?? ''
    const dark = blockOf('html.dark') ?? ''

    expect(light, `:root 缺 ${token}`).toContain(`${token}:`)
    expect(dark, `html.dark 缺 ${token}（暗色下该令牌会沿用明色值）`).toContain(`${token}:`)
  })
})

describe('设计令牌：样式里不写魔法颜色', () => {
  const COLOR_RE = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/g

  it('组件与页面样式只使用令牌，不出现十六进制/rgb() 颜色', () => {
    const offenders: string[] = []

    for (const { file, css } of CSS_TEXTS) {
      if (file === TOKENS_FILE) continue // 令牌来源，颜色在这里落地
      for (const line of stripComments(css).split('\n')) {
        const hit = line.match(COLOR_RE)
        if (hit) {
          offenders.push(`${relative(SRC_DIR, file)}: ${line.trim()}`)
        }
      }
    }

    expect(offenders, `以下样式绕过了设计令牌：\n${offenders.join('\n')}`).toEqual([])
  })

  it('index.css 不含魔法颜色（它是全局重置，最该干净）', () => {
    const indexCss = cssOf(join(SRC_DIR, 'assets', 'styles', 'index.css'))

    expect(stripComments(indexCss).match(COLOR_RE)).toBeNull()
  })
})
