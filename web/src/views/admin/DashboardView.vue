<!--
  DashboardView.vue - 后台首页：站点概况统计卡 + 最近提交
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>站点概况</h2>
      </div>
    </header>
    <div class="stat-cards">
      <div v-for="s in cards" :key="s.label" class="stat-card">
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>

    <div class="section">
      <h4>最近提交</h4>
      <el-table :data="pagedRecent" size="small" height="calc(100vh - 320px)">
        <el-table-column label="ID" width="180">
          <template #default="{ row }">
            <span class="mono-id" :title="row.id">{{ row.id }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="120" />
        <el-table-column prop="problem_title" label="题目" min-width="160" />
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="language" label="语言" width="110" />
        <el-table-column prop="time_ms" label="耗时(ms)" width="90" />
        <el-table-column prop="memory_kb" label="内存(KB)" width="90" />
      </el-table>
      <div v-if="recentTotal > recentPageSize" class="pager-row">
        <el-pagination class="pager" layout="total, prev, pager, next"
                       :total="recentTotal" :page-size="recentPageSize"
                       v-model:current-page="recentPage" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api/client'
import { useClientPager } from '../../composables/useClientPager'

const overview = ref<any>({})
const recent = ref<any[]>([])

// 后续如需拉取更长的提交流，页面已预留分页
const { page: recentPage, size: recentPageSize, total: recentTotal, paged: pagedRecent } =
  useClientPager(computed<any[]>(() => recent.value), 10)

const cards = computed(() => [
  { label: '用户数', value: overview.value.users ?? '-' },
  { label: '题目数', value: overview.value.problems ?? '-' },
  { label: '提交总数', value: overview.value.submissions ?? '-' },
  { label: '今日提交', value: overview.value.today_submissions ?? '-' },
  { label: '今日打卡', value: overview.value.today_checkins ?? '-' },
  { label: '等待队列', value: overview.value.waiting ?? '-' },
  { label: '在线节点', value: overview.value.online_nodes ?? '-' },
])

const statusTag = (s: string) =>
  ({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
     re: 'danger', ce: 'info', se: 'danger', waiting: 'info', judging: 'info' }[s] ?? 'info') as any

async function load() {
  overview.value = await api.get('/admin/overview') as any
  const subs = await api.get('/admin/submissions?page=1&page_size=10') as any
  recent.value = subs.items ?? []
}

onMounted(load)
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.page-title { margin: 0 0 16px; }
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
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
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
