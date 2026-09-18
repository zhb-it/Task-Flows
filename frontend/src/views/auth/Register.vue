<script setup lang="ts">
/**
 * 注册页（前端规格 §8）。
 *
 * 对接 `POST /api/v1/auth/register`（`app/api/v1/auth.py`，成功返回 201 与
 * `UserRead`）。成功后按规格 §8 跳回登录页。
 *
 * 两处校验的取舍必须说清楚，因为「前端校验严于后端」是会挡掉正常用户的：
 *
 * 1. **邮箱格式**：后端 `UserCreate.email` 只是 `str`，不做格式校验。规格 §8
 *    明确要求「邮箱格式正确」，所以前端保留了格式校验——它挡掉的是明显错误的
 *    输入，不影响后端接受的合法邮箱。
 * 2. **密码长度**：规格 §8 写「密码长度符合后端要求」，但后端**没有任何**长度
 *    要求（`UserCreate.password: str`，Service 层也只做哈希）。按项目规则
 *    「不允许猜测」，这里只校验必填与非空。若后续后端加了长度约束，改这里。
 */

import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { Lock, Message, User } from '@element-plus/icons-vue'

import { authApi } from '@/api/auth'
import type { RegisterRequest } from '@/types/auth'

/** 表单比请求体多一个「确认密码」，它不上行。 */
interface RegisterForm extends RegisterRequest {
  confirmPassword: string
}

const router = useRouter()

const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive<RegisterForm>({
  username: '',
  email: '',
  password: '',
  confirmPassword: '',
})

function validateConfirmPassword(
  _rule: unknown,
  value: string,
  callback: (error?: Error) => void,
): void {
  if (!value) {
    callback(new Error('请再次输入密码'))
    return
  }
  if (value !== form.password) {
    callback(new Error('两次输入的密码不一致'))
    return
  }
  callback()
}

const rules: FormRules<RegisterForm> = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  // `required` 这一条不只是语义：Element Plus 只在规则里存在 `required` 时
  // 才渲染必填星号。只挂 validator 会让本页四个必填字段里唯独「确认密码」
  // 没有星号，用户会以为可以不填（视觉实证时发现的）。
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    { validator: validateConfirmPassword, trigger: 'blur' },
  ],
}

async function handleSubmit(): Promise<void> {
  const valid = await formRef.value?.validate().catch(() => false)
  if (valid !== true) {
    return
  }

  submitting.value = true
  try {
    await authApi.register({
      username: form.username,
      email: form.email,
      password: form.password,
    })
    ElMessage.success('注册成功，请使用新账号登录')
    await router.replace({ name: 'login' })
  } catch {
    // 409（用户名/邮箱已注册）等提示由请求层统一弹出。
  } finally {
    submitting.value = false
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

    <el-form-item label="邮箱" prop="email">
      <el-input
        v-model="form.email"
        :prefix-icon="Message"
        placeholder="请输入邮箱"
        autocomplete="email"
      />
    </el-form-item>

    <el-form-item label="密码" prop="password">
      <el-input
        v-model="form.password"
        type="password"
        show-password
        :prefix-icon="Lock"
        placeholder="请输入密码"
        autocomplete="new-password"
      />
    </el-form-item>

    <el-form-item label="确认密码" prop="confirmPassword">
      <el-input
        v-model="form.confirmPassword"
        type="password"
        show-password
        :prefix-icon="Lock"
        placeholder="请再次输入密码"
        autocomplete="new-password"
        @keyup.enter="handleSubmit"
      />
    </el-form-item>

    <el-form-item>
      <el-button type="primary" class="tf-auth__submit" :loading="submitting" @click="handleSubmit">
        注册
      </el-button>
    </el-form-item>

    <div class="tf-auth__link">
      <span>已有账号？</span>
      <router-link :to="{ name: 'login' }">返回登录</router-link>
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
