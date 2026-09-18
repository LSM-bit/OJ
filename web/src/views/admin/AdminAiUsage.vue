<!--
  AdminAiUsage.vue - 后台「AI 用量」看板（阶段8-C）
  数据源 GET /admin/ai-usage?days=N：totals 统计卡 / 按日双轴折线（轮数+token）/
  工具分布横向柱 / Top10 活跃用户表。echarts 按需引入（本路由懒加载，chunk 天然隔离）。
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>AI 助手用量</h2>
      </div>
      <el-radio-group v-model="days" size="small" @change="load">
        <el-radio-button :value="7">近 7 天</el-radio-button>
        <el-radio-button :value="14">近 14 天</el-radio-button>
        <el-radio-button :value="30">近 30 天</el-radio-button>
        <el-radio-button :value="90">近 90 天</el-radio-button>
      </el-radio-group>
    </header>

    <div class="stat-cards">
      <div v-for="s in cards" :key="s.label" class="stat-card">
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>

    <div class="section" v-loading="loading">
      <h4>用量趋势</h4>
      <div ref="trendRef" class="chart chart-trend" />
      <div class="chart-row">
        <div class="chart-half">
          <h4>工具调用分布</h4>
          <div ref="toolsRef" class="chart chart-tools" />
        </div>
        <div class="chart-half">
          <h4>活跃用户 Top 10</h4>
          <el-table :data="pagedTopUsers" size="small" max-height="300">
            <el-table-column type="index" label="#" width="50" />
            <el-table-column prop="username" label="用户" min-width="140" />
            <el-table-column prop="rounds" label="对话轮数" width="110" />
          </el-table>
          <div v-if="topUsersTotal > topUsersPageSize" class="pager-row">
            <el-pagination class="pager" layout="total, prev, pager, next"
                           :total="topUsersTotal" :page-size="topUsersPageSize"
                           v-model:current-page="topUsersPage" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { api } from '../../api/client'
import { useClientPager } from '../../composables/useClientPager'

// 按需注册：只引入折线/柱图 + 三组件 + canvas 渲染器，避免全量 echarts 进包
echarts.use([LineChart, BarChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

// 工具名 → 中文（与助手侧过程提示同源；未注册的按原名显示）
const TOOL_CN: Record<string, string> = {
  get_problem: '查看题目',
  get_submission: '查看提交',
  list_case_results: '核对测试点',
  run_on_sample: '样例试跑',
  search_problems: '搜索题目',
  get_my_stats: '刷题统计',
  get_hint: '整理提示',
  get_problem_full: '查看完整题目',
  get_problem_stats: '题目通过统计',
}

const days = ref(14)
const loading = ref(false)
const usage = ref<any>({})

// 用户规模增长时该表会变长：预留分页
const { page: topUsersPage, size: topUsersPageSize, total: topUsersTotal, paged: pagedTopUsers } =
  useClientPager(computed<any[]>(() => usage.value.top_users ?? []), 10)

const trendRef = ref<HTMLElement>()
const toolsRef = ref<HTMLElement>()
const trendChart = shallowRef<echarts.ECharts>()
const toolsChart = shallowRef<echarts.ECharts>()
let ro: ResizeObserver | null = null

const cards = computed(() => {
  const t = usage.value.totals || {}
  return [
    { label: `近 ${days.value} 天对话轮数`, value: t.rounds ?? '-' },
    { label: '活跃用户', value: t.users ?? '-' },
    { label: '输入 Token', value: fmt(t.input_tokens) },
    { label: '输出 Token', value: fmt(t.output_tokens) },
    { label: '工具调用', value: t.tool_calls ?? '-' },
  ]
})

function fmt(n?: number) {
  if (n == null) return '-'
  return n >= 10000 ? `${(n / 1000).toFixed(1)}k` : String(n)
}

/** Element Plus 主题色（跟随 --el-color-primary，未来 dark 模式零成本） */
function themeColor(fallback = '#409eff') {
  const c = getComputedStyle(document.documentElement)
    .getPropertyValue('--el-color-primary').trim()
  return c || fallback
}

async function load() {
  loading.value = true
  try {
    usage.value = await api.get('/admin/ai-usage', { params: { days: days.value } }) as any
    await nextTick()
    renderTrend()
    renderTools()
  } finally {
    loading.value = false
  }
}

function renderTrend() {
  if (!trendRef.value) return
  if (!trendChart.value) trendChart.value = echarts.init(trendRef.value)
  const daily = usage.value.daily || []
  const primary = themeColor()
  trendChart.value.setOption({
    color: [primary, '#e6a23c'],
    tooltip: { trigger: 'axis' },
    legend: { data: ['对话轮数', '输入 Token', '输出 Token'], top: 0 },
    grid: { left: 50, right: 56, top: 34, bottom: 26 },
    xAxis: { type: 'category', boundaryGap: false,
             data: daily.map((d: any) => d.date.slice(5)) },
    yAxis: [
      { type: 'value', name: '轮数', minInterval: 1 },
      { type: 'value', name: 'Token', splitLine: { show: false } },
    ],
    series: [
      { name: '对话轮数', type: 'line', data: daily.map((d: any) => d.rounds),
        areaStyle: { opacity: 0.08 }, smooth: true },
      { name: '输入 Token', type: 'line', yAxisIndex: 1,
        data: daily.map((d: any) => d.input_tokens), smooth: true },
      { name: '输出 Token', type: 'line', yAxisIndex: 1,
        data: daily.map((d: any) => d.output_tokens), smooth: true },
    ],
  }, true)
}

function renderTools() {
  if (!toolsRef.value) return
  if (!toolsChart.value) toolsChart.value = echarts.init(toolsRef.value)
  const tools: any[] = usage.value.tools || []
  const rows = [...tools].reverse()  // 横向柱状图 y 轴自下而上，反转使最大在顶
  toolsChart.value.setOption({
    color: [themeColor()],
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 90, right: 30, top: 8, bottom: 24 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category',
             data: rows.map((t) => TOOL_CN[t.tool] ?? t.tool) },
    series: [{ name: '调用次数', type: 'bar', barMaxWidth: 18,
               itemStyle: { borderRadius: [0, 4, 4, 0] },
               label: { show: true, position: 'right' },
               data: rows.map((t) => t.count) }],
  }, true)
  // 无数据时给出空态占位，避免空白画布
  if (!rows.length) {
    toolsChart.value.setOption({ title: { text: '暂无工具调用', left: 'center', top: 'middle',
      textStyle: { color: '#909399', fontSize: 13, fontWeight: 400 } } })
  }
}

onMounted(() => {
  load()
  ro = new ResizeObserver(() => { trendChart.value?.resize(); toolsChart.value?.resize() })
  if (trendRef.value) ro.observe(trendRef.value)
  if (toolsRef.value) ro.observe(toolsRef.value)
})

onBeforeUnmount(() => {
  ro?.disconnect()
  trendChart.value?.dispose()
  toolsChart.value?.dispose()
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
  margin-bottom: 16px;
}
.page-title { margin: 0; }
.stat-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 20px;
}
.stat-card {
  flex: 1;
  min-width: 110px;
  padding: 14px 16px;
  background: var(--oj-surface);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
}
.stat-value { font-size: 24px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--oj-ink-3); margin-top: 4px; }
.section h4 { margin: 0 0 10px; }
.chart { width: 100%; }
.chart-trend { height: 300px; margin-bottom: 18px; }
.chart-row { display: flex; gap: 20px; flex-wrap: wrap; }
.chart-half { flex: 1; min-width: 320px; }
.chart-tools { height: 264px; }
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

/* 管理后台 */
.admin-aside {
  background: var(--oj-surface-2);
  border-right: 1px solid var(--oj-line);
}
.admin-logo {
  font-family: var(--oj-font-display);
  letter-spacing: -0.01em;
}
.admin-logo,
.admin-back { border-bottom: 1px solid var(--oj-line-soft); }
.badges { display: flex; align-items: center; gap: var(--oj-s1); }
.log-list { background: var(--oj-surface); }
.log-row {
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.log-time { font-family: var(--oj-font-mono); color: var(--oj-ink-4); }
.node-card {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease);
}
.node-card:hover { border-color: var(--oj-line-strong); box-shadow: var(--oj-shadow-1); }
.chart {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
}
.rename-tip { color: var(--oj-ink-3); font-size: var(--oj-fs-sm); }
.preview {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: var(--oj-s3) var(--oj-s4);
}

/* ===== 逻辑复查：统一标题区与分页行 ===== */
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { margin: 0; font-size: 26px; letter-spacing: -0.02em; }
.head-ops { display: flex; align-items: center; gap: var(--oj-s2); flex-wrap: wrap; }
.pager-row { display: flex; justify-content: flex-end; padding: var(--oj-s3) 0; }
</style>
