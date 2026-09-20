<!--
  SubmissionsView.vue - 我的提交记录列表
  顶栏「提交记录」入口；行点击进入 /submissions/:id 详情页
  按题目筛选：下拉可输入按题名/题号模糊搜索；候选 = 公开题 + 我管理的题（含草稿，
  保证对私有题的提交也能筛到、题目列能显示标题而不是纯 ID）
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Submissions</span>
        <h2>提交记录</h2>
      </div>
      <div class="head-ops">
        <el-button size="small" @click="showFilter = true">
          筛选题目{{ problemId ? `：${problemTitle(problemId)}` : '' }}
        </el-button>
        <el-button v-if="problemId" size="small" text @click="clearFilter">清除</el-button>
      </div>
    </header>

    <el-table :data="pagedItems" v-loading="loading" height="calc(100dvh - 272px)"
              class="click-table" @row-click="(row: any) => $router.push(`/submissions/${row.id}`)">
      <el-table-column label="ID" width="130">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ shortId(row.id) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="题目" min-width="220">
        <template #default="{ row }">
          {{ problemTitle(row.problem_id) }}
        </template>
      </el-table-column>
      <el-table-column prop="language" label="语言" width="110" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="score" label="分数" width="80" align="right" />
      <el-table-column prop="time_ms" label="耗时(ms)" width="100" align="right" />
      <el-table-column label="内存" width="100" align="right">
        <template #default="{ row }">{{ (row.memory_kb / 1024).toFixed(1) }}MB</template>
      </el-table-column>
      <el-table-column label="提交时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.submitted_at) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && items.length === 0" description="暂无提交记录" />

    <div class="pager-row">
      <el-pagination v-if="items.length > pageSize" class="pager"
                     layout="total, prev, pager, next, jumper"
                     :total="items.length" :page-size="pageSize"
                     v-model:current-page="page" />
    </div>

    <!-- 题目筛选：候选 = 公开题 + 我管理的题（含草稿），数量多，下拉过长，拆成弹窗做搜索选择 -->
    <el-dialog v-model="showFilter" title="筛选题目" width="520" append-to-body>
      <el-input v-model="filterKw" placeholder="输入题名 / 题号搜索" clearable />
      <div class="filter-list">
        <div v-for="p in filteredProblems" :key="p.id" class="filter-item"
             :class="{ 'is-active': String(p.id) === String(problemId) }"
             @click="pickProblem(p)">
          <span class="fi-id">{{ p.display_id }}</span>
          <span class="fi-title">{{ p.title }}</span>
        </div>
        <el-empty v-if="filteredProblems.length === 0" description="无匹配题目" :image-size="60" />
      </div>
      <template #footer>
        <el-button v-if="problemId" @click="clearFilter">清除筛选</el-button>
        <el-button type="primary" @click="showFilter = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import { shortId } from '../utils/format'
import { useUserStore } from '../stores/user'

const route = useRoute()
const userStore = useUserStore()
const items = ref<any[]>([])
const problems = ref<any[]>([])
// 雪花 ID 经 json-bigint 前端统一为 string，筛选值与选项 value 同型才能正确预选
const problemId = ref<string | null>(null)
const loading = ref(false)

// 客户端分页：接口一次性返回该用户最近 50 条提交，页面内做分页展示
const page = ref(1)
const pageSize = 15
const pagedItems = computed(() =>
  items.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch(items, () => {
  if ((page.value - 1) * pageSize >= items.value.length) page.value = 1
})

// 题目筛选弹窗
const showFilter = ref(false)
const filterKw = ref('')
const filteredProblems = computed(() => {
  const kw = filterKw.value.trim().toLowerCase()
  const list = kw
    ? problems.value.filter((p) => `${p.display_id}. ${p.title}`.toLowerCase().includes(kw))
    : problems.value
  return list.slice(0, 300)
})
function pickProblem(p: any) {
  problemId.value = String(p.id)
  showFilter.value = false
  reload()
}
function clearFilter() {
  problemId.value = null
  showFilter.value = false
  reload()
}

const statusTag = (s: string) =>
  ({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
     re: 'danger', ce: 'info', se: 'danger', waiting: 'info', judging: 'info' }[s] ?? 'info') as any

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 19) : '')

const problemTitle = (pid: number | string) => {
  const p = problems.value.find((x) => String(x.id) === String(pid))
  return p ? `${p.display_id}. ${p.title}` : `#${pid}`
}

async function load() {
  loading.value = true
  try {
    items.value = await api.get('/submissions', {
      params: { problem_id: problemId.value || undefined },
    }) as any
  } finally {
    loading.value = false
  }
}

function reload() {
  page.value = 1
  load()
}

async function loadProblems() {
  // 候选 = 公开题 + 我管理的题（含草稿）：对草稿/私有题的提交也要能筛到、能显示标题
  // size=1000：默认分页只有 50 条，标题映射/筛选会缺题（后端上限 1000）
  try {
    const [pub, mine] = await Promise.all([
      api.get('/problems', { params: { size: 1000 } }) as Promise<any[]>,
      userStore.isLoggedIn ? (api.get('/problems', { params: { mine: 1, size: 1000 } }) as Promise<any[]>)
                           : Promise.resolve([] as any[]),
    ])
    const seen = new Set<string>()
    problems.value = [...pub, ...mine].filter((p) => {
      if (seen.has(String(p.id))) return false
      seen.add(String(p.id))
      return true
    })
  } catch { /* 忽略：候选加载失败不阻塞提交列表 */ }
}

onMounted(async () => {
  // 支持从出题中心等页面带 ?problem=<id> 跳入，直接预选本题的提交
  if (route.query.problem) problemId.value = String(route.query.problem)
  load()
  await loadProblems()
  // 列表轮询刷新（等待判题的提交状态会变化）
  timer = window.setInterval(load, 5000)
})

let timer: number | undefined
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.page {
  height: 100%;
  padding: var(--oj-s5) var(--oj-s6) 0;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s4);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s4);
}
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { font-size: 26px; letter-spacing: -0.02em; }

.click-table {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}
.click-table :deep(tbody tr) { cursor: pointer; }
.mono-id {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  color: var(--oj-ink-3);
  white-space: nowrap;
}
.head-ops { display: flex; align-items: center; gap: var(--oj-s2); }

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0 var(--oj-s4);
}

/* 筛选弹窗内的题目列表：可滚动、悬停/选中态清晰 */
.filter-list {
  margin-top: var(--oj-s3);
  max-height: 46vh;
  overflow-y: auto;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
}
.filter-item {
  display: flex;
  align-items: center;
  gap: var(--oj-s3);
  padding: 8px var(--oj-s4);
  cursor: pointer;
  border-bottom: 1px solid var(--oj-line-soft);
  transition: background var(--oj-dur-1) var(--oj-ease),
              color var(--oj-dur-1) var(--oj-ease);
}
.filter-item:last-child { border-bottom: none; }
.filter-item:hover { background: var(--oj-surface-2); }
.filter-item.is-active { background: var(--oj-accent-soft); }
.filter-item.is-active .fi-title { color: var(--oj-accent); }
.fi-id {
  min-width: 54px;
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-sm);
  color: var(--oj-ink-4);
}
.fi-title { font-size: var(--oj-fs-md); }
</style>
