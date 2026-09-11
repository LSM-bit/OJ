<!--
  AdminSubmissions.vue - 后台提交管理：全站提交流水（5s 轮询）+ 筛选 + 详情/重判
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="filters.user_id" placeholder="用户ID" clearable style="width: 110px"
                @change="reload" />
      <el-input v-model="filters.problem_id" placeholder="题目ID" clearable style="width: 110px"
                @change="reload" />
      <el-select v-model="filters.status" placeholder="状态" clearable style="width: 130px"
                 @change="reload">
        <el-option v-for="(label, key) in STATUS_OPTIONS" :key="key" :label="label" :value="key" />
      </el-select>
      <el-button type="primary" @click="reload">刷新</el-button>
    </div>

    <el-table :data="items" v-loading="loading" height="calc(100vh - 220px)" size="small">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column label="用户" width="200">
        <template #default="{ row }">
          <div class="user-cell">
            <span class="mono-id" :title="row.user_id">{{ row.user_id }}</span>
            <span class="username">{{ row.username }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="题目" min-width="160">
        <template #default="{ row }">
          <span :title="row.problem_id">#{{ row.problem_id }} {{ row.problem_title }}</span>
        </template>
      </el-table-column>
      <el-table-column label="比赛" width="200">
        <template #default="{ row }">{{ row.contest_id ? `#${row.contest_id}` : '-' }}</template>
      </el-table-column>
      <el-table-column prop="language" label="语言" width="100" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="分数" width="70" />
      <el-table-column prop="time_ms" label="耗时" width="70" />
      <el-table-column prop="memory_kb" label="内存" width="80" />
      <el-table-column label="时间" width="160">
        <template #default="{ row }">{{ fmtTime(row.submitted_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openDetail(row)">详情</el-button>
          <el-button size="small" text type="warning" :disabled="!row.has_code"
                     @click="rejudge(row)">重判</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :page-size="pageSize" :current-page="page"
                   @current-change="(p: number) => { page = p; load() }" />

    <!-- 提交详情 -->
    <el-dialog v-model="showDetail" title="提交详情" width="720">
      <template v-if="detail">
        <el-descriptions :column="3" size="small" border>
          <el-descriptions-item label="ID">
            <span class="mono-id">{{ detail.id }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status_label }}</el-descriptions-item>
          <el-descriptions-item label="得分">{{ detail.score }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ detail.time_ms }} ms</el-descriptions-item>
          <el-descriptions-item label="内存">{{ detail.memory_kb }} KB</el-descriptions-item>
          <el-descriptions-item label="语言">{{ detail.language }}</el-descriptions-item>
        </el-descriptions>
        <p v-if="detail.error_message" class="err-msg">错误信息：{{ detail.error_message }}</p>
        <h4>源码</h4>
        <pre class="code-block">{{ detail.code ?? '（旧提交未留存源码）' }}</pre>
        <h4>测试点</h4>
        <el-table :data="detail.detail ?? []" size="small" max-height="220">
          <el-table-column prop="idx" label="#" width="60" />
          <el-table-column prop="status" label="状态" />
          <el-table-column prop="time_used_ms" label="耗时(ms)" />
          <el-table-column prop="memory_used_kb" label="内存(KB)" />
        </el-table>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'

const STATUS_OPTIONS: Record<string, string> = {
  waiting: '等待判题', judging: '判题中', ac: '通过', wa: '答案错误', tle: '超时',
  mle: '超内存', re: '运行错误', ce: '编译错误', ole: '输出超限', se: '系统错误',
}

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 30
const loading = ref(false)
const filters = reactive({ user_id: '', problem_id: '', status: '' })

const showDetail = ref(false)
const detail = ref<any>(null)

const statusTag = (s: string) =>
  ({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
     re: 'danger', ce: 'info', se: 'danger', waiting: 'info', judging: 'info' }[s] ?? 'info') as any

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 19) : '')

async function load() {
  loading.value = true
  try {
    const r = await api.get('/admin/submissions', {
      params: {
        page: page.value,
        page_size: pageSize,
        user_id: filters.user_id || undefined,
        problem_id: filters.problem_id || undefined,
        status_q: filters.status || undefined,
      },
    }) as any
    items.value = r.items ?? []
    total.value = r.total ?? 0
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

async function openDetail(row: any) {
  detail.value = await api.get(`/admin/submissions/${row.id}`) as any
  showDetail.value = true
}

async function rejudge(row: any) {
  try {
    const r = await api.post(`/admin/submissions/${row.id}/rejudge`) as any
    ElMessage.success(`重判完成：${r.status_label}，得分 ${r.score}`)
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '重判失败')
  }
}

// 5 秒轮询实时刷新（一期不引 WebSocket）
let timer: number | undefined
onMounted(() => {
  load()
  timer = window.setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 10px;
  justify-content: flex-end;
}
.err-msg { color: var(--el-color-danger); font-size: 13px; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.user-cell .username {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.code-block {
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
