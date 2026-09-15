<script setup lang="ts">
/**
 * 业务页占位组件（前端阶段 2 使用，后续阶段实现真实页面时逐个替换）。
 *
 * 为什么要有这层占位而不是空白页：规格 §43 明令列表为空时不能出现空白页，
 * 而未实现的页面本质上就是「功能为空」。占位页把三件事讲清楚——
 * 这是哪个页面、属于哪个阶段、将调用哪些接口——避免后来者以为是漏做。
 *
 * `api` 里的端点**照抄 `docs/API_CONTRACT.md`**，不凭印象写（规格 §57）。
 */

defineProps<{
  title: string
  /** 前端阶段编号（规格 §59 的开发顺序）。 */
  phase: string
  /** 该页面将调用的后端端点，例如 `GET /api/v1/projects`。 */
  api?: string[]
  /** 额外说明：契约上的限制、设计上的取舍。 */
  note?: string
}>()
</script>

<template>
  <div class="tf-page">
    <el-card shadow="never">
      <template #header>
        <span class="tf-placeholder__title">{{ title }}</span>
      </template>

      <el-empty>
        <template #description>
          <p class="tf-placeholder__desc">该页面将在前端{{ phase }}实现</p>
          <div v-if="api && api.length > 0" class="tf-placeholder__api">
            <p class="tf-placeholder__label">计划调用的接口</p>
            <ul>
              <li v-for="endpoint in api" :key="endpoint">
                <code>{{ endpoint }}</code>
              </li>
            </ul>
          </div>
          <el-alert
            v-if="note"
            class="tf-placeholder__note"
            type="info"
            :closable="false"
            :title="note"
            show-icon
          />
        </template>
      </el-empty>
    </el-card>
  </div>
</template>

<style scoped>
.tf-placeholder__title {
  font-weight: 600;
}

.tf-placeholder__desc {
  margin: 0 0 12px;
  color: #606266;
}

.tf-placeholder__api {
  text-align: left;
  max-width: 460px;
  margin: 0 auto 12px;
}

.tf-placeholder__label {
  margin: 0 0 4px;
  font-size: 12px;
  color: #909399;
}

.tf-placeholder__api ul {
  margin: 0;
  padding-left: 18px;
  color: #606266;
  font-size: 13px;
}

.tf-placeholder__note {
  text-align: left;
  max-width: 460px;
  margin: 0 auto;
}
</style>
