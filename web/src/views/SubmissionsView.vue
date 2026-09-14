<!--
  SubmissionsView.vue - 我的提交记录列表
  顶栏「提交记录」入口；行点击进入 /submissions/:id 详情页
  按题目筛选：下拉可输入按题名/题号模糊搜索；候选 = 公开题 + 我管理的题（含草稿，
  保证对私有题的提交也能筛到、题目列能显示标题而不是纯 ID）
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>我的提交记录</h2>
      <el-select v-model="problemId" placeholder="搜索题名/题号筛选" clearable filterable
                 style="width: 260px" @change="reload">
        <el-option v-for="p in problems" :key="p.id"
                   :label="`${p.display_id}. ${p.title}`" :value="p.id" />
      </el-select>
    </div>

    <el-table :data="items" v-loading="loading" height="calc(100vh - 170px)"
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
      <el-table-column prop="score" label="分数" width="80" />
      <el-table-column prop="time_ms" label="耗时(ms)" width="100" />
      <el-table-column label="内存" width="100">
        <template #default="{ row }">{{ (row.memory_kb / 1024).toFixed(1) }}MB</template>
      </el-table-column>
      <el-table-column label="提交时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.submitted_at) }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && items.length === 0" description="暂无提交记录" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
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
  padding: 16px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.click-table :deep(tbody tr) { cursor: pointer; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
</style>
