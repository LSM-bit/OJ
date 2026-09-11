<!--
  DashboardView.vue - 后台首页：站点概况统计卡 + 最近提交
-->
<template>
  <div class="page">
    <h2 class="page-title">站点概况</h2>
    <div class="stat-cards">
      <div v-for="s in cards" :key="s.label" class="stat-card">
        <div class="stat-value">{{ s.value }}</div>
        <div class="stat-label">{{ s.label }}</div>
      </div>
    </div>

    <div class="section">
      <h4>最近提交</h4>
      <el-table :data="recent" size="small" height="calc(100vh - 320px)">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api/client'

const overview = ref<any>({})
const recent = ref<any[]>([])

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
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
}
.stat-value { font-size: 24px; font-weight: 700; color: var(--el-color-primary); }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.section h4 { margin: 0 0 10px; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
</style>
