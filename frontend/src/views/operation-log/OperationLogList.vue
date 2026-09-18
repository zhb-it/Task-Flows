<script setup lang="ts">
/**
 * 操作日志（前端规格 §32 / §44 / 阶段 13）。
 *
 * 数据源：`GET /logs` —— 后端只返回**当前用户自己**的操作时间线（资源级
 * 隔离，无需资源归属校验）。相对规格 §32 的完整清单，以下是**诚实降级**
 * （全部源于真实契约，见 docs/FRONTEND_API_MAPPING.md §4-D16，不编造接口）：
 *
 * 1. 「操作人筛选 / 操作人列」无意义——时间线本身就是「我的」，全部条目
 *    操作人都是当前用户，后端也不返回用户名字段，故不设该列；
 * 2. 「时间筛选 / 操作类型筛选」——`GET /logs` 只有 `skip`/`limit` 参数，
 *    没有任何筛选参数 → 两种筛选均做在**当前已取回的页**上（客户端过滤），
 *    页面顶部明示；
 * 3. 「IP 列」——`OperationLogRead` 没有 IP 字段，后端审计未记录 IP，无法展示；
 * 4. 分页无 `total`（响应为裸数组）→ 「上一页 / 下一页」形态，以「本页是否
 *    取满 pageSize」推断是否有下一页并如实提示；`limit` 上限 100。
 *
 * payload 是后端原样透传的 JSONB，按 action 收窄展示；未知 action 原样展示
 * action 字符串、payload 走 JSON 兜底（后端埋点逐业务接入，当前已知三种）。
 */
import { computed, onMounted, ref } from 'vue'
import { Document, Search } from '@element-plus/icons-vue'
import { logApi } from '@/api/log'
import { useAuthStore } from '@/stores/auth'
import { formatDateTime } from '@/utils/format'
import EmptyState from '@/components/common/EmptyState.vue'
import {
  operationActionLabel,
  resourceTypeLabel,
  type OperationLog,
  type OperationLogAction,
} from '@/types/log'
import { TASK_STATUS_LABELS, type TaskStatus } from '@/types/task'

const PAGE_SIZE = 20

const auth = useAuthStore()

const logs = ref<OperationLog[]>([])
const loading = ref(false)
const loadError = ref(false)
const page = ref(1)
/** 下一页是否存在：本页取满 pageSize 即「可能有」，否则确定没有。 */
const hasMore = ref(false)

/** 操作类型筛选（客户端，作用于当前已取回的页）。 */
const actionFilter = ref<'all' | OperationLogAction>('all')
const ACTION_OPTIONS: Array<{ value: OperationLogAction; label: string }> = [
  { value: 'task:transition', label: '任务状态流转' },
  { value: 'comment:delete', label: '删除评论' },
  { value: 'attachment:delete', label: '删除附件' },
]

/** 时间范围筛选（客户端，作用于当前已取回的页）。 */
const timeRange = ref<[string, string] | null>(null)

const filteredLogs = computed<OperationLog[]>(() => {
  let rows = logs.value
  if (actionFilter.value !== 'all') {
    rows = rows.filter((log) => log.action === actionFilter.value)
  }
  if (timeRange.value) {
    const [start, end] = timeRange.value
    rows = rows.filter((log) => {
      const t = log.created_at
      return (!start || t >= start) && (!end || t <= end)
    })
  }
  return rows
})

const isFiltered = computed(
  () => actionFilter.value !== 'all' || timeRange.value !== null,
)

async function loadLogs(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    const rows = await logApi.listMyLogs({
      skip: (page.value - 1) * PAGE_SIZE,
      limit: PAGE_SIZE,
    })
    logs.value = rows
    hasMore.value = rows.length === PAGE_SIZE
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function goPage(delta: number): void {
  const target = page.value + delta
  if (target < 1 || (delta > 0 && !hasMore.value)) return
  page.value = target
  void loadLogs()
}

function resetFilters(): void {
  actionFilter.value = 'all'
  timeRange.value = null
}

/**
 * payload → 人类可读描述。按后端当前实际写入的三种 action 收窄：
 * - task:transition → `{old_status, new_status}`（§15 示例的原始形状）
 * - comment:delete → `{task_id, comment_id}`
 * - attachment:delete → `{task_id, attachment_id, filename}`
 * 未知 action / 字段缺失一律 JSON 兜底，不假定 payload 形状。
 */
function describePayload(log: OperationLog): string {
  const p = log.payload
  if (log.action === 'task:transition') {
    const oldStatus = typeof p.old_status === 'string' ? p.old_status : null
    const newStatus = typeof p.new_status === 'string' ? p.new_status : null
    if (oldStatus && newStatus) {
      const label = (s: string) =>
        (TASK_STATUS_LABELS as Record<string, string>)[s as TaskStatus] ?? s
      return `状态 ${label(oldStatus)} → ${label(newStatus)}`
    }
  }
  if (log.action === 'comment:delete') {
    if (typeof p.task_id === 'number' && typeof p.comment_id === 'number') {
      return `删除任务 #${p.task_id} 中的评论 #${p.comment_id}`
    }
  }
  if (log.action === 'attachment:delete') {
    if (typeof p.task_id === 'number' && typeof p.filename === 'string') {
      return `删除任务 #${p.task_id} 的附件「${p.filename}」`
    }
  }
  return JSON.stringify(p)
}

function describeResource(log: OperationLog): string {
  return `${resourceTypeLabel(log.resource_type)} #${log.resource_id}`
}

onMounted(loadLogs)
</script>

<template>
  <div class="log-page">
    <h2 class="log-page__title">操作日志</h2>

    <el-alert
      class="log-page__alert"
      type="info"
      :closable="false"
      show-icon
      title="本页只展示你自己的操作时间线（后端资源级隔离）"
      description="后端 GET /logs 没有 total、筛选与 IP 字段：操作类型 / 时间筛选仅作用于当前已取回的页；分页为上一页/下一页形态；规格中的「操作人」列与「IP」列因后端不返回相应数据而无法展示。"
    />

    <el-card shadow="never">
      <div class="log-page__toolbar">
        <el-select v-model="actionFilter" class="log-page__filter" size="default">
          <el-option label="全部操作" value="all" />
          <el-option
            v-for="opt in ACTION_OPTIONS"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <el-date-picker
          v-model="timeRange"
          class="log-page__filter"
          type="datetimerange"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DDTHH:mm:ss"
        />
        <el-button v-if="isFiltered" text type="primary" @click="resetFilters">
          清除筛选
        </el-button>
        <span v-if="isFiltered" class="log-page__filter-note">
          筛选仅作用于当前已取回的页（第 {{ page }} 页）
        </span>
      </div>

      <el-table
        v-loading="loading"
        :data="filteredLogs"
        row-key="id"
      >
        <!-- 空态分两种（TASK-130）：筛选把当前页筛空了 → 给「清除筛选」；
             本来就没有日志 → 说明日志是自动记录的，没有可执行的下一步。 -->
        <template #empty>
          <EmptyState
            :icon="isFiltered ? Search : Document"
            :title="isFiltered ? '当前页没有匹配的操作' : '还没有操作日志'"
            :description="
              isFiltered
                ? '筛选只作用于当前已取回的这一页；清空筛选或翻页后再看。'
                : '你在团队、项目、任务上的写操作会自动记录在这里（仅自己可见）。'
            "
            size="sm"
          >
            <template v-if="isFiltered" #actions>
              <el-button @click="resetFilters">清除筛选</el-button>
            </template>
          </EmptyState>
        </template>
        <el-table-column label="操作" min-width="220">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ operationActionLabel(row.action) }}</el-tag>
            <span class="log-page__payload">{{ describePayload(row as OperationLog) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资源" width="160">
          <template #default="{ row }">{{ describeResource(row as OperationLog) }}</template>
        </el-table-column>
        <el-table-column label="时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>

      <div class="log-page__pager">
        <el-button :disabled="page <= 1 || loading" @click="goPage(-1)">上一页</el-button>
        <span class="log-page__pager-info">第 {{ page }} 页</span>
        <el-button :disabled="!hasMore || loading" @click="goPage(1)">下一页</el-button>
      </div>
      <p v-if="isFiltered" class="log-page__pager-hint">
        已显示第 {{ page }} 页中筛选后的 {{ filteredLogs.length }} 条；翻页后需重新应用筛选。
      </p>
    </el-card>

    <el-alert
      v-if="loadError"
      class="log-page__alert"
      type="error"
      :closable="false"
      show-icon
      :title="`日志加载失败${auth.currentUser ? '' : '（未获取到登录用户）'}，请稍后重试`"
    />
  </div>
</template>

<style scoped>
.log-page__title {
  margin: 0 0 16px;
  font-weight: 600;
}

.log-page__alert {
  margin-bottom: 16px;
}

.log-page__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.log-page__filter {
  width: 220px;
}

.log-page__filter-note {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.log-page__payload {
  margin-left: 8px;
  color: var(--el-text-color-regular);
}

.log-page__pager {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.log-page__pager-info {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.log-page__pager-hint {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-align: right;
}
</style>
