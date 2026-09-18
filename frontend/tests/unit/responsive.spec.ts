/* eslint-disable vue/one-component-per-file -- 测试桩必须定义多个轻量组件（el-* 桩 + 布局子组件桩），单文件多组件在测试里是合理形态 */
/**
 * 主框架响应式形态的单元测试（TASK-130）。
 *
 * `use-breakpoint.spec.ts` 只保证「断点算得对」，这里保证「算完之后用对了」——
 * 侧栏在窄屏与宽屏下是**两套不同的 DOM 结构**（`el-drawer` 浮层 vs `el-aside`
 * 常驻），`BasicLayout` 用 `v-if` / `v-else` 二选一。这两条分支最大的风险不是
 * 写错，而是**只改了其中一条**：断点从 992 调到 768 却漏改另一边，宽屏开发机
 * 上看不出任何异常，到了手机上侧栏直接消失或常驻侧栏把内容挤成一条缝。
 *
 * 因此这里不测像素，只钉死**结构契约**：任一宽度下必须恰好存在一套形态。
 *
 * 挂载说明：项目走 Element Plus 按需引入（`unplugin-vue-components` 只在
 * `vite.config.ts` 生效），测试环境里 `el-*` 是未注册标签。所以这里用渲染函数
 * 手写轻量桩，而不是 `template` 字符串（vitest 解析的是 runtime-only 构建，
 * 运行时模板编译不可用）。
 */

import { mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { defineComponent, h, nextTick } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import BasicLayout from '@/layouts/BasicLayout.vue'
import { DRAWER_WIDTH, MOBILE_BREAKPOINT } from '@/composables/useBreakpoint'

/** 断点内侧（仍算窄屏）与断点本身（算宽屏）。 */
const NARROW = MOBILE_BREAKPOINT - 1
const WIDE = MOBILE_BREAKPOINT

// --- Element Plus 桩：只保留本组件真正依赖的能力 -------------------------

const ElContainerStub = defineComponent({
  name: 'ElContainer',
  setup: (_, { slots }) => () => h('div', slots.default?.()),
})

const ElHeaderStub = defineComponent({
  name: 'ElHeader',
  setup: (_, { slots }) => () => h('div', slots.default?.()),
})

const ElMainStub = defineComponent({
  name: 'ElMain',
  setup: (_, { slots }) => () => h('div', slots.default?.()),
})

/** 抽屉桩：把 `size` / `modelValue` 落到 data 属性上供断言读取。 */
const ElDrawerStub = defineComponent({
  name: 'ElDrawer',
  props: {
    modelValue: { type: Boolean, default: false },
    size: { type: [String, Number], default: '' },
    direction: { type: String, default: '' },
    withHeader: { type: Boolean, default: true },
  },
  emits: ['update:modelValue'],
  setup: (props, { slots }) => () =>
    h(
      'div',
      { class: 'stub-drawer', 'data-size': String(props.size) },
      slots.default?.(),
    ),
})

/** 常驻侧栏桩：`width` 是本组件传给 EP 的原始宽度表达式，正好用于断言折叠态。 */
const ElAsideStub = defineComponent({
  name: 'ElAside',
  props: { width: { type: String, default: '' } },
  setup: (props, { slots }) => () =>
    h('div', { class: 'stub-aside', 'data-width': props.width }, slots.default?.()),
})

// --- 子组件桩：本文件只关心「谁被渲染、拿到了什么 props」 -------------------

const AppHeaderStub = defineComponent({
  name: 'AppHeader',
  props: {
    collapsed: { type: Boolean, default: false },
    isMobile: { type: Boolean, default: false },
    drawerOpen: { type: Boolean, default: false },
  },
  emits: ['toggle-sidebar'],
  setup: () => () => h('div', { class: 'stub-header' }),
})

const AppSidebarStub = defineComponent({
  name: 'AppSidebar',
  props: { collapsed: { type: Boolean, default: false } },
  setup: () => () => h('div', { class: 'stub-sidebar' }),
})

/** 设置视口宽度并触发 resize（jsdom 不会自己改 innerWidth）。 */
function setViewport(width: number): void {
  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    writable: true,
    value: width,
  })
  window.dispatchEvent(new Event('resize'))
}

async function buildRouter(): Promise<Router> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { render: () => null } }],
  })
  await router.push('/')
  return router
}

/** 在指定宽度下挂载主框架。调用方负责 `unmount()`（见 `afterEach`）。 */
async function mountLayout(width: number): Promise<VueWrapper> {
  setViewport(width)
  const router = await buildRouter()
  return mount(BasicLayout, {
    global: {
      plugins: [router],
      components: {
        ElContainer: ElContainerStub,
        ElHeader: ElHeaderStub,
        ElMain: ElMainStub,
        ElDrawer: ElDrawerStub,
        ElAside: ElAsideStub,
      },
      stubs: {
        AppHeader: AppHeaderStub,
        AppSidebar: AppSidebarStub,
        AppBreadcrumb: true,
      },
    },
  })
}

const drawer = (w: VueWrapper) => w.findComponent(ElDrawerStub)
const aside = (w: VueWrapper) => w.findComponent(ElAsideStub)

let wrapper: VueWrapper | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('BasicLayout 响应式形态', () => {
  it('窄屏渲染抽屉浮层，不渲染常驻侧栏', async () => {
    wrapper = await mountLayout(NARROW)

    expect(drawer(wrapper).exists()).toBe(true)
    expect(aside(wrapper).exists()).toBe(false)
  })

  it('宽屏渲染常驻侧栏，不渲染抽屉', async () => {
    wrapper = await mountLayout(WIDE)

    expect(aside(wrapper).exists()).toBe(true)
    expect(drawer(wrapper).exists()).toBe(false)
  })

  it('两套形态互斥：任一宽度下恰好存在一套（不会两套都渲染或都不渲染）', async () => {
    for (const width of [NARROW, WIDE]) {
      const w = await mountLayout(width)
      const count = Number(drawer(w).exists()) + Number(aside(w).exists())
      expect(count, `${width}px 下渲染了 ${count} 套侧栏形态`).toBe(1)
      w.unmount()
    }
  })

  it('跨过断点时两套形态整体互换（防止只改一条分支）', async () => {
    wrapper = await mountLayout(WIDE)
    expect(aside(wrapper).exists()).toBe(true)

    setViewport(NARROW)
    await nextTick()

    expect(drawer(wrapper).exists()).toBe(true)
    expect(aside(wrapper).exists()).toBe(false)

    setViewport(WIDE)
    await nextTick()

    expect(aside(wrapper).exists()).toBe(true)
    expect(drawer(wrapper).exists()).toBe(false)
  })

  it('抽屉宽度取自 DRAWER_WIDTH 常量（改常量不会漏改使用处）', async () => {
    wrapper = await mountLayout(NARROW)

    expect(drawer(wrapper).attributes('data-size')).toBe(DRAWER_WIDTH)
  })

  it('抽屉形态下侧栏始终不折叠（抽屉宽度本身就是完整宽度）', async () => {
    wrapper = await mountLayout(NARROW)

    expect(wrapper.findComponent(AppSidebarStub).props('collapsed')).toBe(false)
  })

  it('宽屏点顶栏按钮是折叠侧栏，不动抽屉状态', async () => {
    wrapper = await mountLayout(WIDE)

    expect(aside(wrapper).attributes('data-width')).toBe('var(--tf-sidebar-width)')

    wrapper.findComponent(AppHeaderStub).vm.$emit('toggle-sidebar')
    await nextTick()

    expect(aside(wrapper).attributes('data-width')).toBe(
      'var(--tf-sidebar-collapsed-width)',
    )
    expect(drawer(wrapper).exists()).toBe(false)
  })

  it('窄屏点顶栏按钮是开合抽屉', async () => {
    wrapper = await mountLayout(NARROW)
    const header = wrapper.findComponent(AppHeaderStub)

    expect(header.props('drawerOpen')).toBe(false)

    header.vm.$emit('toggle-sidebar')
    await nextTick()
    expect(header.props('drawerOpen')).toBe(true)

    header.vm.$emit('toggle-sidebar')
    await nextTick()
    expect(header.props('drawerOpen')).toBe(false)
  })

  it('窗口变宽时抽屉自行关闭（不留下「回到窄屏还开着」的残留状态）', async () => {
    wrapper = await mountLayout(NARROW)
    const header = wrapper.findComponent(AppHeaderStub)

    header.vm.$emit('toggle-sidebar')
    await nextTick()
    expect(header.props('drawerOpen')).toBe(true)

    setViewport(WIDE)
    await nextTick()
    setViewport(NARROW)
    await nextTick()

    expect(wrapper.findComponent(AppHeaderStub).props('drawerOpen')).toBe(false)
  })

  it('宽屏顶栏拿到 isMobile=false，窄屏拿到 true（顶栏按钮语义由它决定）', async () => {
    wrapper = await mountLayout(WIDE)
    expect(wrapper.findComponent(AppHeaderStub).props('isMobile')).toBe(false)

    setViewport(NARROW)
    await nextTick()
    expect(wrapper.findComponent(AppHeaderStub).props('isMobile')).toBe(true)
  })
})
