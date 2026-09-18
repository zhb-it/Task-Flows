/**
 * 空状态与新手引导组件的渲染断言（TASK-130）。
 *
 * 这两个组件是「用户第一次打开产品时看到的东西」，它们的价值全在**文案与
 * 出口**上，所以测试也盯着这两点：
 *
 * - `EmptyState`：标题/描述必须渲染；有动作槽时必须有可点的出口，没给动作槽
 *   时不出现空的按钮区（否则页面底部会多出一条空白）。
 * - `GettingStarted`：三步必须按「建团队 → 建项目 → 分任务」的顺序出现，且
 *   **当前步唯一**（第一个未完成的步骤），主按钮指向当前步的目标页——这是引导
 *   的全部意义：不让新用户同时面对三个平级选择。
 *
 * Element Plus 组件在 vitest 里没有被 `unplugin-vue-components` 转换（那是构建
 * 期的事），因此显式 stub：这样断言的是我们自己的结构，不是 EP 的内部实现。
 */

import { mount, type VueWrapper } from '@vue/test-utils'
import { routerKey } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import EmptyState from '@/components/common/EmptyState.vue'
import GettingStarted from '@/components/common/GettingStarted.vue'

/** 透传 `click` 的按钮替身：让「点主按钮会跳哪儿」可以被断言。 */
const ElButtonStub = {
  name: 'ElButton',
  props: ['type', 'icon', 'text', 'size', 'disabled', 'loading'],
  emits: ['click'],
  template: '<button class="stub-button" @click="$emit(\'click\')"><slot /></button>',
}

describe('EmptyState', () => {
  it('渲染标题与描述，并以 role=status 宣告（读屏可感知）', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '还没有项目', description: '建一个项目开始拆任务。' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.attributes('role')).toBe('status')
    expect(wrapper.find('.tf-empty__title').text()).toBe('还没有项目')
    expect(wrapper.find('.tf-empty__desc').text()).toBe('建一个项目开始拆任务。')
  })

  it('没有描述时不渲染描述段落（不留空行）', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '没有匹配的命令' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.find('.tf-empty__desc').exists()).toBe(false)
  })

  it('没有动作槽时不渲染动作区', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '还没有操作日志' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.find('.tf-empty__actions').exists()).toBe(false)
  })

  it('动作槽走 #actions，渲染出真实可点的 DOM（不是空壳）', async () => {
    const onClick = vi.fn()
    const wrapper = mount(EmptyState, {
      props: { title: '还没有项目' },
      slots: { actions: '<button class="cta">创建项目</button>' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.find('.tf-empty__actions').exists()).toBe(true)
    const cta = wrapper.find('button.cta')
    expect(cta.exists()).toBe(true)
    expect(cta.text()).toBe('创建项目')

    cta.element.addEventListener('click', onClick)
    await cta.trigger('click')
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('不写 #actions 时，默认槽同样放在动作区（调用方少记一个槽名）', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '还没有团队' },
      slots: { default: '<button class="cta">创建团队</button>' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.find('.tf-empty__actions button.cta').exists()).toBe(true)
  })

  it('size=sm 收紧尺寸（表格内/卡片内的小空态）', () => {
    const wrapper = mount(EmptyState, {
      props: { title: '暂无数据', size: 'sm' },
      global: { stubs: { 'el-icon': true } },
    })

    expect(wrapper.classes()).toContain('tf-empty--sm')
  })
})

describe('GettingStarted', () => {
  function mountStart(props: { teams: number; projects: number; tasks: number }): {
    wrapper: VueWrapper
    push: ReturnType<typeof vi.fn>
  } {
    const push = vi.fn()
    const wrapper = mount(GettingStarted, {
      props,
      global: {
        provide: { [routerKey]: { push } },
        stubs: { 'el-button': ElButtonStub, 'el-icon': true },
      },
    })
    return { wrapper, push }
  }

  it('三步按「建团队 → 建项目 → 分任务」的顺序渲染', () => {
    const { wrapper } = mountStart({ teams: 0, projects: 0, tasks: 0 })

    const titles = wrapper.findAll('.tf-start__step-title').map((n) => n.text())
    expect(titles).toHaveLength(3)
    expect(titles[0]).toContain('建一个团队')
    expect(titles[1]).toContain('在团队下建项目')
    expect(titles[2]).toContain('拆出第一个任务并分配')
  })

  it('全空账号：当前步是第一步，主按钮指向 /teams', async () => {
    const { wrapper, push } = mountStart({ teams: 0, projects: 0, tasks: 0 })

    const steps = wrapper.findAll('.tf-start__step')
    expect(steps[0].classes()).toContain('tf-start__step--current')
    expect(steps[1].classes()).not.toContain('tf-start__step--current')

    const primary = steps[0].find('.stub-button')
    expect(primary.text()).toBe('创建团队')
    await primary.trigger('click')
    expect(push).toHaveBeenCalledWith('/teams')
  })

  it('已建团队未建项目：第一步标记完成，当前步推进到第二步', async () => {
    const { wrapper, push } = mountStart({ teams: 1, projects: 0, tasks: 0 })

    const steps = wrapper.findAll('.tf-start__step')
    expect(steps[0].classes()).toContain('tf-start__step--done')
    expect(steps[0].text()).toContain('已完成')
    expect(steps[1].classes()).toContain('tf-start__step--current')

    await steps[1].find('.stub-button').trigger('click')
    expect(push).toHaveBeenCalledWith('/projects')
    expect(wrapper.find('.tf-start__progress-num').text()).toBe('1')
  })

  it('三步都完成：没有当前步，进度显示 3/3', () => {
    const { wrapper } = mountStart({ teams: 1, projects: 2, tasks: 9 })

    const steps = wrapper.findAll('.tf-start__step')
    expect(steps.every((s) => s.classes().includes('tf-start__step--done'))).toBe(true)
    expect(steps.some((s) => s.classes().includes('tf-start__step--current'))).toBe(false)
    expect(wrapper.find('.tf-start__progress-num').text()).toBe('3')
  })

  it('只强调当前一步：同屏最多一个主按钮', () => {
    const { wrapper } = mountStart({ teams: 1, projects: 0, tasks: 0 })

    // 主按钮只在当前步渲染；其余步骤给的是次级链接按钮
    expect(wrapper.findAll('.tf-start__step--current .stub-button')).toHaveLength(1)
  })
})
