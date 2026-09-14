<!--
  ContestDetailView.vue - 比赛详情页（参考牛客 OJ）
  上方：比赛信息头（状态/赛制/时间/倒计时/报名按钮，管理者显示「编辑」入口）
  Tab：比赛题目（管理者可批量重测）| 排行榜（ACM 罚时/封榜气泡）| 公告（管理者可发布）
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
          <el-button v-if="contest.is_manageable" size="small" @click="openEdit">
            <el-icon style="margin-right:4px"><Edit /></el-icon>编辑
          </el-button>
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
            <el-table-column label="操作" :width="contest.is_manageable ? 160 : 100" align="center">
              <template #default="{ row }">
                <el-button v-if="userStore.isLoggedIn" type="primary" plain size="small"
                           @click="toggleSubmit(row)">提交</el-button>
                <el-button v-if="contest.is_manageable" type="warning" plain size="small"
                           :loading="rejudging === row.alias"
                           @click="rejudgeProblem(row)">重测</el-button>
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

        <el-tab-pane label="公告" name="announcements">
          <!-- 管理者发布框 -->
          <div v-if="contest.is_manageable" class="ann-editor">
            <h4>发布公告</h4>
            <el-input v-model="annForm.title" size="small" maxlength="128" show-word-limit
                      placeholder="公告标题（如：A 题数据已更新，请注意重交）" style="margin-bottom:8px" />
            <el-input v-model="annForm.content" type="textarea" :rows="4" maxlength="10000"
                      placeholder="公告内容（支持说明澄清、勘误、数据更新等）" />
            <div style="margin-top:8px">
              <el-button type="primary" size="small" :loading="annPosting"
                         :disabled="!annForm.title.trim()" @click="postAnnouncement">发布公告</el-button>
            </div>
          </div>
          <el-empty v-if="announcements.length === 0" description="暂无公告" :image-size="60" />
          <div v-else class="ann-list">
            <div v-for="a in announcements" :key="a.id" class="ann-item">
              <div class="ann-head">
                <span class="ann-title">{{ a.title }}</span>
                <span class="ann-meta">{{ a.author_name }} · {{ fmtFull(a.created_at) }}</span>
              </div>
              <div class="ann-content">{{ a.content }}</div>
            </div>
          </div>
        </el-tab-pane>

        <el-tab-pane v-if="userStore.isLoggedIn" label="提交记录" name="submissions" lazy>
          <div class="subs-toolbar">
            <el-select v-model="subsFilter.alias" placeholder="题目" clearable size="small"
                       style="width:120px" @change="reloadSubs">
              <el-option v-for="p in contest.problems" :key="p.alias"
                         :label="`${p.alias}. ${p.title}`" :value="p.alias" />
            </el-select>
            <el-input v-if="subs.can_view_all" v-model="subsFilter.username"
                      placeholder="用户名" clearable size="small" style="width:140px"
                      @change="reloadSubs" />
            <el-button size="small" @click="loadSubs">刷新</el-button>
            <span v-if="!subs.can_view_all" class="form-tip">仅显示你自己的提交</span>
            <span v-else class="form-tip">管理者视图：可查看所有人的提交</span>
          </div>
          <el-table :data="subs.items" stripe size="small" v-loading="subsLoading">
            <el-table-column label="ID" width="120">
              <template #default="{ row }">
                <span class="mono-id">{{ shortId(row.id) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="username" label="用户" width="110" />
            <el-table-column prop="problem_alias" label="题号" width="70" align="center" />
            <el-table-column prop="language" label="语言" width="110" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="score" label="分数" width="70" align="center" />
            <el-table-column prop="time_ms" label="耗时(ms)" width="90" align="center" />
            <el-table-column prop="memory_kb" label="内存(KB)" width="90" align="center" />
            <el-table-column label="提交时间" min-width="140">
              <template #default="{ row }">{{ fmtFull(row.submitted_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="70" align="center">
              <template #default="{ row }">
                <el-button size="small" text type="primary" @click="openSubDetail(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-pagination v-if="subs.total > subsPageSize" class="pager"
                         layout="total, prev, pager, next" :total="subs.total"
                         :page-size="subsPageSize" :current-page="subsPage"
                         @current-change="(p: number) => { subsPage = p; loadSubs() }" />

          <!-- 提交详情弹窗 -->
          <el-dialog v-model="showSubDetail" title="提交详情" width="720">
            <template v-if="subDetail">
              <el-descriptions :column="3" size="small" border>
                <el-descriptions-item label="ID">
                  <span class="mono-id" :title="subDetail.id">{{ shortId(subDetail.id) }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="题目">{{ subDetail.problem_alias }}</el-descriptions-item>
                <el-descriptions-item label="语言">{{ subDetail.language }}</el-descriptions-item>
                <el-descriptions-item label="状态">
                  <el-tag size="small" :type="statusTag(subDetail.status)">{{ subDetail.status_label }}</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="得分">{{ subDetail.score }}</el-descriptions-item>
                <el-descriptions-item label="耗时/内存">
                  {{ subDetail.time_ms }} ms / {{ subDetail.memory_kb }} KB
                </el-descriptions-item>
              </el-descriptions>
              <p v-if="subDetail.error_message" class="err-msg">错误信息：{{ subDetail.error_message }}</p>
              <h4>源码</h4>
              <pre class="code-block">{{ subDetail.code ?? '（旧提交未留存源码）' }}</pre>
              <h4>测试点</h4>
              <el-table v-if="subDetail.detail?.length" :data="subDetail.detail" size="small" max-height="220">
                <el-table-column prop="idx" label="#" width="60" />
                <el-table-column prop="status" label="状态" />
                <el-table-column prop="time_used_ms" label="耗时(ms)" />
                <el-table-column prop="memory_used_kb" label="内存(KB)" />
              </el-table>
              <p v-else class="form-tip">
                {{ contest.phase === 'running' ? '比赛结束后可见测试点明细' : '暂无测试点数据' }}
              </p>
            </template>
          </el-dialog>
        </el-tab-pane>
      </el-tabs>

      <!-- 编辑比赛时间（仅结束前） -->
      <el-dialog v-model="showEdit" title="编辑比赛时间" width="460">
        <el-form label-width="90px" size="small">
          <el-form-item label="开始时间">
            <el-date-picker v-model="editForm.start_at" type="datetime"
                            value-format="YYYY-MM-DDTHH:mm:ss"
                            placeholder="选择开始时间" style="width:100%" />
          </el-form-item>
          <el-form-item label="结束时间">
            <el-date-picker v-model="editForm.end_at" type="datetime"
                            value-format="YYYY-MM-DDTHH:mm:ss"
                            placeholder="选择结束时间" style="width:100%" />
          </el-form-item>
          <el-form-item label="封榜(分钟)">
            <el-input-number v-model="editForm.board_freeze_minutes" :min="0" :max="10080"
                             style="width:100%" />
            <span class="form-tip">0 表示不封榜；封榜 = 结束前 N 分钟冻结榜单</span>
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button size="small" @click="showEdit = false">取消</el-button>
          <el-button type="primary" size="small" :loading="saving" @click="saveEdit">保存</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Edit } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { shortId } from '../utils/format'
import { useUserStore } from '../stores/user'

const route = useRoute()
const userStore = useUserStore()

const contest = ref<any>(null)
const problems = ref<any[]>([])
const standings = ref<any>(null)
const loading = ref(true)
const tab = ref('problems')
const registered = ref(false)

// 公告
const announcements = ref<any[]>([])
const annForm = reactive({ title: '', content: '' })
const annPosting = ref(false)

// 时间编辑（管理者）
const showEdit = ref(false)
const saving = ref(false)
const editForm = reactive({ start_at: '', end_at: '', board_freeze_minutes: 0 })

// 批量重测
const rejudging = ref('')

// 提交记录（登录用户可见；管理者可看所有人并按用户名筛选）
const subs = ref({ total: 0, items: [], can_view_all: false })
const subsFilter = reactive({ alias: '', username: '' })
const subsPage = ref(1)
const subsPageSize = 20
const subsLoading = ref(false)

function statusTag(s: string) {
  return (({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
             re: 'danger', ce: 'info', se: 'danger',
             waiting: 'info', judging: 'info' } as Record<string, any>)[s]) ?? 'info'
}

async function loadSubs() {
  subsLoading.value = true
  try {
    const params: Record<string, any> = { page: subsPage.value, page_size: subsPageSize }
    if (subsFilter.alias) params.problem_alias = subsFilter.alias
    if (subs.value.can_view_all && subsFilter.username) params.username = subsFilter.username
    subs.value = await api.get(`/contests/${route.params.id}/submissions`, { params }) as any
  } finally {
    subsLoading.value = false
  }
}

async function reloadSubs() {
  subsPage.value = 1
  await loadSubs()
}

// 提交详情弹窗（源码/测试点明细，由后端按权限与比赛阶段裁剪）
const showSubDetail = ref(false)
const subDetail = ref<any>(null)

async function openSubDetail(row: any) {
  subDetail.value = await api.get(
    `/contests/${route.params.id}/submissions/${row.id}`) as any
  showSubDetail.value = true
}

// 切到「提交记录」tab 时加载数据（lazy tab 首次激活才渲染，需主动触发）
watch(tab, (v) => { if (v === 'submissions') reloadSubs() })

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

// ---------- 管理功能 ----------

function openEdit() {
  // 日期选择器需要本地时间格式；把 ISO 时间转成 YYYY-MM-DDTHH:mm:ss（本地）
  const toLocal = (iso: string) => {
    const d = new Date(iso)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  }
  editForm.start_at = toLocal(contest.value.start_at)
  editForm.end_at = toLocal(contest.value.end_at)
  editForm.board_freeze_minutes = contest.value.board_freeze_minutes ?? 0
  showEdit.value = true
}

async function saveEdit() {
  if (!editForm.start_at || !editForm.end_at) {
    ElMessage.warning('请选择开始和结束时间')
    return
  }
  if (new Date(editForm.end_at) <= new Date(editForm.start_at)) {
    ElMessage.warning('结束时间必须晚于开始时间')
    return
  }
  saving.value = true
  try {
    contest.value = await api.patch(`/contests/${contest.value.id}`, {
      start_at: new Date(editForm.start_at).toISOString(),
      end_at: new Date(editForm.end_at).toISOString(),
      board_freeze_minutes: editForm.board_freeze_minutes,
    }) as any
    showEdit.value = false
    ElMessage.success('比赛时间已更新')
    await loadStandings()  // 封榜窗口可能变化，刷新榜单
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

async function rejudgeProblem(row: any) {
  try {
    await ElMessageBox.confirm(
      `确认重测 ${row.alias} 题的全部提交？该题所有提交将重新判题并覆盖结果（排行榜随之更新）。`,
      '批量重测', { confirmButtonText: '重测', cancelButtonText: '取消', type: 'warning' })
  } catch {
    return
  }
  rejudging.value = row.alias
  try {
    const r = await api.post(
      `/contests/${contest.value.id}/problems/${row.alias}/rejudge`) as any
    ElMessage.success(
      `重测完成：成功 ${r.rejudged} 条` +
      (r.skipped ? `，跳过 ${r.skipped} 条（无源码）` : '') +
      (r.failed ? `，失败 ${r.failed} 条` : ''))
    await loadStandings()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '重测失败')
  } finally {
    rejudging.value = ''
  }
}

async function loadAnnouncements() {
  announcements.value = await api.get(`/contests/${route.params.id}/announcements`) as any
}

async function postAnnouncement() {
  if (!annForm.title.trim()) return
  annPosting.value = true
  try {
    await api.post(`/contests/${contest.value.id}/announcements`, {
      title: annForm.title.trim(), content: annForm.content }) as any
    annForm.title = ''
    annForm.content = ''
    ElMessage.success('公告已发布')
    await loadAnnouncements()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '发布失败')
  } finally {
    annPosting.value = false
  }
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
    await Promise.all([loadStandings(), loadAnnouncements()])
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

/* 公告 */
.ann-editor {
  padding: 12px 16px;
  margin-bottom: 16px;
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}
.ann-editor h4 { margin: 0 0 8px; }
.ann-list { display: flex; flex-direction: column; gap: 12px; }
.ann-item {
  padding: 12px 16px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: #fff;
}
.ann-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.ann-title { font-weight: 600; }
.ann-meta { color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; }
.ann-content {
  margin-top: 6px;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--el-text-color-regular);
}
.form-tip { color: var(--el-text-color-placeholder); font-size: 12px; }

/* 提交记录 */
.subs-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Monaco, monospace;
  font-size: 12px;
  white-space: nowrap;
}
.err-msg { color: var(--el-color-danger); font-size: 13px; }
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
