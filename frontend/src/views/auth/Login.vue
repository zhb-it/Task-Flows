<script setup lang="ts">
/**
 * 登录页（前端规格 §7）。
 *
 * 对接真实后端 `POST /api/v1/auth/login`（`app/api/v1/auth.py`）。流程：
 * 提交 → `authStore.login()`（换令牌 + 拉 `/users/me`）→ 回跳 `?redirect=` 或进首页。
 *
 * 关于密码校验只有「必填」：规格 §7 写「表单验证」，但没有给出长度规则，而后端
 * `LoginRequest` 对 `password` 也只声明了 `str`（无长度约束）。按项目规则
 * 「不允许猜测」，前端不发明后端不存在的规则——否则用户会看到一个后端根本不
 * 在意的报错。注册页同此处理（见 `Register.vue` 的注释）。
 *
 * 登录失败的具体文案由请求层的统一错误处理弹出（规格 §41），这里只负责收尾。
 */

import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import { useAuthStore } from '@/stores/auth'
import type { LoginRequest } from '@/types/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const formRef = ref<FormInstance>()

const form = reactive<LoginRequest>({ username: '', password: '' })

const rules: FormRules<LoginRequest> = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleSubmit(): Promise<void> {
  // `validate()` 校验失败时以 reject 表达，转成布尔值更直白。
  const valid = await formRef.value?.validate().catch(() => false)
  if (valid !== true) {
    return
  }

  try {
    await auth.login({ ...form })
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    await router.replace(redirect || { name: 'dashboard' })
  } catch {
    // 失败提示已由请求层统一弹出（401 用户名或密码错误 / 403 账号已禁用）。
  }
}
</script>

<template>
  <el-form
    ref="formRef"
    :model="form"
    :rules="rules"
    label-position="top"
    @submit.prevent="handleSubmit"
  >
    <el-form-item label="用户名" prop="username">
      <el-input
        v-model="form.username"
        :prefix-icon="User"
        placeholder="请输入用户名"
        autocomplete="username"
      />
    </el-form-item>

    <el-form-item label="密码" prop="password">
      <el-input
        v-model="form.password"
        type="password"
        show-password
        :prefix-icon="Lock"
        placeholder="请输入密码"
        autocomplete="current-password"
        @keyup.enter="handleSubmit"
      />
    </el-form-item>

    <el-form-item>
      <el-button type="primary" class="tf-auth__submit" :loading="auth.loggingIn" @click="handleSubmit">
        登录
      </el-button>
    </el-form-item>

    <div class="tf-auth__link">
      <span>没有账号？</span>
      <router-link :to="{ name: 'register' }">立即注册</router-link>
    </div>
  </el-form>
</template>

<style scoped>
.tf-auth__submit {
  width: 100%;
}

.tf-auth__link {
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
