<!--
  ContestDetailView.vue - 比赛详情页（参考牛客 OJ）
  上方：比赛信息头（状态/赛制/时间/倒计时/报名按钮）
  Tab：比赛题目 | 排行榜（ACM 罚时/封榜气泡）| 公告
  题目 tab 内点击题目行内展开提交框，比赛内提交
-->
<template>
  <div v-loading="loading" class="page">
    <template v-if="contest">
      <!-- 比赛信息头 -->
      <div class="contest-header">
        <div class="ch-top">
          <el-tag :type="phaseTag(contest.phase)" effect="dark" size="small">{{ phaseLabel(contest.phase) }}</el-tag>
          <h2 class="ch-title">{{ contest.title }}</h2>
          <el-button
            v-if="userStore.isLoggedIn"
            type="primary" size="small"
            :disabled="registered || contest.phase !== 'running'"
            @click="register"
          >
            {{ registered ? '已报名' : '立即报名' }}
          </el-button>
        </div>
        <div class="ch-meta">
          <span>{{ ruleLabel(contest.rule) }}</span>
          <span class="divider">|</span>
          <span>{{ fmtFull(contest.start_at) }} ~ {{ fmtFull(contest.end_at) }}</span>
          <span class="divider">|</span>
          <span v-if="contest.phase === 'running'" class="countdown">剩余 {{ countdown }}</span>
          <span v-else-if="contest.phase === 'upcoming'">尚未开始</span>
          <span v-else>已结束</span>
          <template v-if="contest.board_freeze_minutes > 0">
            <span class="divider">|</span>
            <span>赛前 {{ contest.board_freeze_minutes }} 分钟封榜</span>
          </template>
        </div>
      </div>

      <!-- Tab 区 -->
      <el-tabs v-model="tab" class="contest-tabs">
        <el-tab-pane label="比赛题目" name="problems">
          <el-table :data="problems" stripe>
            <el-table-column prop="alias" label="#" width="60">
              <template #default="{ row }">
                <span class="alias">{{ row.alias }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="title" label="题目名称" min-width="220">
              <template #default="{ row }">
                <el-link v-if="row.visible" type="primary" :underline="false"
                         @click="$router.push(`/contests/${contest.id}/problems/${row.alias}`)">
                  {{ row.title }}
                </el-link>
                <span v-else class="muted">（无权查看）</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag v-if="cellOf(row)" :type="cellTag(cellOf(row))" size="small">
                  {{ cellText(cellOf(row)) }}
                </el-tag>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="时间/内存限制" width="160">
              <template #default="{ row }">{{ row.time_limit_ms }}ms / {{ row.memory_limit_mb }}MB</template>
            </el-table-column>
            <el-table-column label="操作" width="100" align="center">
              <template #default="{ row }">
                <el-button v-if="userStore.isLoggedIn" type="primary" plain size="small"
                           @click="toggleSubmit(row)">提交</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 行内提交面板 -->
          <div v-if="submitTarget" class="submit-panel">
            <h4>提交 · {{ submitTarget.alias }}. {{ submitTarget.title }}</h4>
            <el-select v-model="language" size="small" style="width:180px; margin-bottom:8px">
              <el-option label="Python 3.12" value="python3.12" />
              <el-option label="C++17" value="cpp17" />
              <el-option label="C17" value="c17" />
              <el-option label="Java 21" value="java21" />
            </el-select>
            <el-input v-model="code" type="textarea" :rows="12" placeholder="在此粘贴代码..."
                      class="code-input" />
            <div style="margin-top:10px; display:flex; gap:10px; align-items:center">
              <el-button type="primary" size="small" :loading="submitting" @click="submit">提交评测</el-button>
              <el-button size="small" @click="submitTarget = null">取消</el-button>
              <span v-if="lastResult" :class="['sub-result', lastResult.status]">{{ lastResult.status_label }}
                ｜ 耗时 {{ lastResult.time_ms }}ms</span>
            </div>
          </div>
          <el-alert v-if="!userStore.isLoggedIn" type="warning" :closable="false" show-icon
                    title="登录并报名后才能提交" style="margin-top:12px" />
        </el-tab-pane>

        <el-tab-pane label="排行榜" name="standings">
          <div v-if="standings" class="standings-wrap">
            <el-alert v-if="standings.frozen" type="warning" :closable="false" show-icon
                      title="已封榜：封榜期间的提交结果将在比赛结束后揭晓" style="margin-bottom:12px" />
            <el-table :data="standings.rows" stripe size="small">
              <el-table-column prop="rank" label="排名" width="64" align="center">
                <template #default="{ row }">
                  <span :class="['rank', `rank-${row.rank <= 3 ? row.rank : 'n'}`]">{{ row.rank }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="username" label="用户名" min-width="120" />
              <el-table-column prop="solved" label="解题数" width="80" align="center">
                <template #default="{ row }">{{ row.solved }}</template>
              </el-table-column>
              <el-table-column
                v-for="p in contest.problems" :key="p.alias"
                :label="p.alias" width="100" align="center">
                <template #default="{ row }">
                  <div class="cell-bubble" :class="cellClass(row.cells.find((c: any) => c.alias === p.alias))">
                    {{ cellText(row.cells.find((c: any) => c.alias === p.alias)) }}
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="contest.rule === 'acm' ? '罚时' : '总分'" width="90" align="center">
                <template #default="{ row }">{{ row.penalty }}</template>
              </el-table-column>
            </el-table>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const route = useRoute()
const userStore = useUserStore()

const contest = ref<any>(null)
const problems = ref<any[]>([])
const standings = ref<any>(null)
const loading = ref(true)
const tab = ref('problems')
const registered = ref(false)

const submitTarget = ref<any>(null)
const language = ref('python3.12')
const code = ref('')
const submitting = ref(false)
const lastResult = ref<any>(null)

let timer: number | undefined
const now = ref(Date.now())
const countdown = computed(() => {
  const end = new Date(contest.value?.end_at).getTime()
  let s = Math.max(0, Math.floor((end - now.value) / 1000))
  const h = Math.floor(s / 3600); s %= 3600
  const m = Math.floor(s / 60)
  return `${h}:${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
})

const phaseLabel = (p: string) => ({ running: '进行中', upcoming: '未开始', ended: '已结束' }[p] ?? p)
const phaseTag = (p: string) => ({ running: 'success', upcoming: 'warning', ended: 'info' }[p] ?? 'info') as any
const ruleLabel = (r: string) => ({ acm: 'ACM 赛制', oi: 'OI 赛制', ioi: 'IOI 赛制' }[r] ?? r)

function fmtFull(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// 当前用户在某题上的榜单 cell（无则视为未提交）
function cellOf(row: any) {
  const st = standings.value
  if (!st) return null
  const me = st.rows.find((r: any) => r.username === userStore.user?.username)
  return me?.cells.find((c: any) => c.alias === row.alias) ?? null
}
function cellTag(c: any) {
  if (!c) return 'info'
  if (c.solved) return c.frozen ? 'warning' : 'success'
  return 'danger'
}
function cellText(c: any) {
  if (!c) return '—'
  if (c.solved) return c.frozen ? '?' : '通过'
  if (c.pending > 0) return `+${c.pending}`
  if (c.attempts > 0) return `-${c.attempts}`
  return '—'
}
// 排行榜气泡：ACM 风格（绿=过题带时间，黄=封榜待揭晓，灰=尝试次数，暗=未提交）
function cellClass(c: any) {
  if (!c) return 'cell-none'
  if (c.solved) return c.frozen ? 'cell-frozen' : 'cell-solved'
  if (c.pending > 0) return 'cell-pending'
  if (c.attempts > 0) return 'cell-attempts'
  return 'cell-none'
}

function toggleSubmit(row: any) {
  if (submitTarget.value?.alias === row.alias) {
    submitTarget.value = null
    return
  }
  submitTarget.value = row
  lastResult.value = null
  code.value = ''
}

async function register() {
  try {
    await api.post(`/contests/${contest.value.id}/register`)
    registered.value = true
    ElMessage.success('报名成功')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '报名失败')
  }
}

async function submit() {
  if (!code.value.trim()) {
    ElMessage.warning('代码不能为空')
    return
  }
  submitting.value = true
  try {
    lastResult.value = await api.post(
      `/contests/${contest.value.id}/problems/${submitTarget.value.alias}/submit`,
      { language: language.value, code: code.value }) as any
    await loadStandings()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '提交失败')
  } finally {
    submitting.value = false
  }
}

async function loadStandings() {
  standings.value = await api.get(`/contests/${route.params.id}/standings`) as any
  // 检测是否已报名：榜单里有自己即视为已报名（一期简化）
  registered.value = standings.value.rows.some(
    (r: any) => r.username === userStore.user?.username)
}

onMounted(async () => {
  try {
    contest.value = await api.get(`/contests/${route.params.id}`) as any
    // 题目限制信息已随比赛详情下发（time_limit_ms/memory_limit_mb），直接展开
    problems.value = contest.value.problems.map((cp: any) => ({
      ...cp,
      visible: cp.visible,
      alias: cp.alias,
    }))
    await loadStandings()
    timer = window.setInterval(() => { now.value = Date.now() }, 1000)
  } catch {
    ElMessage.error('比赛不存在')
  } finally {
    loading.value = false
  }
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.contest-header {
  padding: 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  margin-bottom: 16px;
}
.ch-top { display: flex; align-items: center; gap: 12px; }
.ch-title { margin: 0; font-size: 20px; flex: 1; }
.ch-meta { margin-top: 10px; color: var(--el-text-color-secondary); font-size: 13px; }
.divider { margin: 0 10px; }
.countdown { color: var(--el-color-danger); font-weight: 600; }
.alias { font-weight: 700; color: var(--el-color-primary); }
.muted { color: var(--el-text-color-placeholder); }

.submit-panel {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}
.submit-panel h4 { margin: 0 0 10px; }
.code-input :deep(textarea) { font-family: Consolas, Monaco, monospace; }
.sub-result { font-size: 13px; font-weight: 600; }
.sub-result.ac { color: var(--el-color-success); }
.sub-result.wa, .sub-result.re, .sub-result.tle, .sub-result.mle { color: var(--el-color-danger); }
.sub-result.ce { color: var(--el-color-warning); }

.standings-wrap { overflow-x: auto; }
.rank { font-weight: 700; }
.rank-1 { color: #e6a23c; }
.rank-2 { color: #909399; }
.rank-3 { color: #b8860b; }
.cell-bubble {
  border-radius: 4px;
  padding: 4px 6px;
  font-size: 12px;
  font-weight: 600;
  min-width: 48px;
  margin: 0 auto;
  display: inline-block;
}
.cell-solved { background: #f0f9eb; color: var(--el-color-success); border: 1px solid #e1f3d8; }
.cell-frozen { background: #fdf6ec; color: var(--el-color-warning); border: 1px solid #faecd8; }
.cell-attempts { background: #fef0f0; color: var(--el-color-danger); border: 1px solid #fde2e2; }
.cell-pending { background: #f4f4f5; color: var(--el-text-color-secondary); border: 1px solid #e9e9eb; }
.cell-none { color: var(--el-text-color-placeholder); }
</style>
