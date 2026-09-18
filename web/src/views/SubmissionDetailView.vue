<!--
  SubmissionDetailView.vue - 提交记录详情页
  状态/得分/耗时/内存 + 测试点逐条明细 + CE 错误信息
  权限：仅本人与 ADMIN 可看（后端 GET /submissions/{id} 强校验）
-->
<template>
  <div v-loading="loading" class="page">
    <template v-if="sub">
      <div class="page-head">
        <div>
          <el-button size="small" text @click="$router.back()">← 返回</el-button>
          <span class="oj-kicker">Submission</span>
          <span class="s-title">提交 <span class="mono-id" :title="sub.id">#{{ shortId(sub.id) }}</span></span>
          <el-tag :type="statusTag(sub.status)" style="margin-left: 10px">{{ sub.status_label }}</el-tag>
        </div>
        <div>
          <el-button v-if="userStore.isLoggedIn" size="small" type="primary" plain
                     @click="askAi">
            <el-icon style="margin-right:2px"><MagicStick /></el-icon>诊断这次错误
          </el-button>
          <el-button v-if="problemId" size="small"
                     @click="$router.push(`/problems/${problemId}`)">查看题目</el-button>
        </div>
      </div>

      <el-descriptions :column="4" border class="meta">
        <el-descriptions-item label="题目">{{ problemTitle }}</el-descriptions-item>
        <el-descriptions-item label="语言">{{ sub.language }}</el-descriptions-item>
        <el-descriptions-item label="得分">{{ sub.score }}</el-descriptions-item>
        <el-descriptions-item label="提交时间">{{ fmtTime(sub.submitted_at) }}</el-descriptions-item>
        <el-descriptions-item label="耗时">{{ sub.time_ms }} ms</el-descriptions-item>
        <el-descriptions-item label="内存">{{ (sub.memory_kb / 1024).toFixed(1) }} MB</el-descriptions-item>
        <el-descriptions-item label="比赛">{{ sub.contest_id ? `#${shortId(sub.contest_id)}` : '—' }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ sub.status_label }}</el-descriptions-item>
      </el-descriptions>

      <el-alert v-if="sub.error_message" type="error" :closable="false" class="ce-box"
                :title="sub.status === 'ce' ? '编译错误信息' : '错误信息'">
        <pre class="err-pre">{{ sub.error_message }}</pre>
      </el-alert>

      <h4 class="sec-title">提交的代码</h4>
      <div class="code-box">
        <CodeEditor v-if="sub.code" :model-value="sub.code" :language="sub.language" :readonly="true"
                    class="code-editor" />
        <pre v-else class="code-fallback">{{ codeText }}</pre>
      </div>

      <h4 class="sec-title">测试点明细</h4>
      <el-table :data="pagedCases" size="small" border>
        <el-table-column prop="idx" label="#" width="70" />
        <el-table-column label="状态" width="180">
          <template #default="{ row }">
            <el-tag size="small" :type="caseTag(row.status)">{{ caseLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="time_used_ms" label="耗时(ms)" width="110" />
        <el-table-column label="内存" width="130">
          <template #default="{ row }">{{ (row.memory_used_kb / 1024).toFixed(1) }} MB</template>
        </el-table-column>
      </el-table>
      <div v-if="caseTotal > casePageSize" class="pager-row">
        <el-pagination class="pager" layout="total, prev, pager, next"
                       :total="caseTotal" :page-size="casePageSize"
                       v-model:current-page="casePage" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { shortId } from '../utils/format'
import { useClientPager } from '../composables/useClientPager'
import { useUserStore } from '../stores/user'
import { useAssistantStore } from '../stores/assistant'
import CodeEditor from '../components/CodeEditor.vue'

const route = useRoute()
const userStore = useUserStore()
const assistant = useAssistantStore()
const sub = ref<any>(null)
const problems = ref<any[]>([])
const loading = ref(true)

// 测试点数量可能很多：前端预留分页
const caseRows = computed<any[]>(() => sub.value?.detail ?? [])
const { page: casePage, size: casePageSize, total: caseTotal, paged: pagedCases } =
  useClientPager(caseRows, 20)

// 「诊断这次错误」：以本次提交为上下文打开助教抽屉（后端 _resolve_context 自动带 problem_id）
function askAi() {
  assistant.openWithContext(
    { type: 'submission', submission_id: sub.value.id },
    `我这次提交判定为「${sub.value.status_label}」，帮我看看问题出在哪`)
}

// 旧提交（code 为 NULL/空）展示占位说明
const codeText = computed(() => (sub.value?.code ? '' : '（旧提交未留存源码）'))

const problemId = computed(() => sub.value?.problem_id)
const problemTitle = computed(() => {
  if (!sub.value) return ''
  const p = problems.value.find((x) => x.id === sub.value.problem_id)
  return p ? `${p.display_id}. ${p.title}` : `#${sub.value.problem_id}`
})

const statusTag = (s: string) =>
  ({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
     re: 'danger', ce: 'warning', se: 'danger', waiting: 'info', judging: 'info' }[s] ?? 'info') as any
const caseTag = statusTag

const CASE_LABEL: Record<string, string> = {
  accepted: '通过', wrong_answer: '答案错误', time_limit_exceeded: '超时',
  memory_limit_exceeded: '超内存', output_limit_exceeded: '输出超限',
  runtime_error: '运行错误', compile_error: '编译错误', system_error: '系统错误',
}
const caseLabel = (s: string) => CASE_LABEL[s] ?? s

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 19) : '')

// 等待判题中的提交 2s 轮询刷新，判完自动停
let timer: number | undefined
async function refresh() {
  const latest = await api.get(`/submissions/${route.params.id}`) as any
  sub.value = latest
  if (!['waiting', 'judging'].includes(latest.status)) {
    clearInterval(timer)
  }
}

onMounted(async () => {
  try {
    sub.value = await api.get(`/submissions/${route.params.id}`) as any
    // size=1000：只为拿题号→标题映射，默认分页 50 条会查不到新题（显示成 #id）
    problems.value = await api.get('/problems', { params: { size: 1000 } }) as any
    if (['waiting', 'judging'].includes(sub.value.status)) {
      timer = window.setInterval(refresh, 2000)
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '无权查看该提交')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.s-title { font-size: 17px; font-weight: 700; margin-left: 8px; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  white-space: nowrap;
}
.meta { margin-bottom: 14px; }
.ce-box { margin-bottom: 14px; }
.err-pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  max-height: 240px;
  overflow-y: auto;
}
.sec-title { margin: 0 0 10px; }
.code-box {
  height: 380px;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
  margin-bottom: 16px;
}
/* Monaco 组件自身带边框，嵌入时铺满并去边框 */
.code-editor :deep(.monaco-container) {
  height: 100%;
  border: none;
  border-radius: 0;
}
.code-fallback {
  margin: 0;
  padding: 12px 14px;
  color: var(--oj-ink-4);
  font-size: 13px;
}
/* ===== 视觉刷新：统一页面骨架（追加层，保证同特异性下胜出） ===== */
.page {
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
}
.page-head,
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.page-head h2,
.page-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s4);
}
.spacer { flex: 1; }
.mono-id,
.mono {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--oj-ink-3);
}
.muted,
.tip,
.pick-hint,
.form-tip,
.data-hint,
.err-msg {
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.section { margin-top: var(--oj-s6); }
.section h4 {
  margin: 0 0 var(--oj-s3);
  font-size: var(--oj-fs-lg);
}
.stat-card {
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.stat-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateY(-1px);
}
.stat-value {
  font-family: var(--oj-font-mono);
  font-size: 26px;
  letter-spacing: -0.02em;
  color: var(--oj-ink);
}
.stat-label {
  margin-top: 4px;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0;
}
.click-table,
.fill-table,
.cases-table,
.verify-table,
.log-list {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}

/* 提交详情 */
.s-title { letter-spacing: -0.02em; }
.meta { color: var(--oj-ink-3); font-size: var(--oj-fs-sm); }
.sec-title {
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--oj-ink-4);
}
.ce-box,
.code-box {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}
.err-pre { font-family: var(--oj-font-mono); }
</style>
