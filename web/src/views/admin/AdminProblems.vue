<!--
  AdminProblems.vue - 后台题目管理：全量列表（含私有）+ 公开性切换
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>题目管理</h2>
      </div>
      <div class="head-ops">
        <el-input v-model="q" placeholder="搜索题目标题" clearable style="width: 220px"
                  @keyup.enter="load" @clear="load" />
        <el-button type="primary" @click="load">搜索</el-button>
      </div>
    </header>

    <el-table :data="pagedItems" v-loading="loading" height="calc(100dvh - 218px)">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="display_id" label="题号" width="70" align="center" />
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column label="归属" width="130">
        <template #default="{ row }">
          <el-tag size="small" :type="row.owner_type === 'team' ? 'warning' : 'info'"
                  :title="row.owner_id">
            {{ row.owner_type === 'team' ? `团队#${row.owner_id}` : `用户#${row.owner_id}` }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可见性" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_public ? 'success' : 'danger'">
            {{ row.is_public ? '公开' : '私有' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="data_version" label="数据版本" width="90" />
      <el-table-column prop="case_count" label="测试点" width="80" align="right" />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button size="small" text type="primary"
                     @click="togglePublic(row, !row.is_public)">
            {{ row.is_public ? '设为私有' : '设为公开' }}
          </el-button>
          <el-button size="small" text @click="$router.push(`/problems/${row.id}`)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager-row">
      <el-pagination v-if="items.length > pageSize" class="pager"
                     layout="total, prev, pager, next"
                     :total="items.length" :page-size="pageSize"
                     v-model:current-page="page" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'

const items = ref<any[]>([])
// 客户端分页：接口一次性返回全量列表，页面内分页展示
const page = ref(1)
const pageSize = 20
const pagedItems = computed(() =>
  items.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch(items, () => {
  if ((page.value - 1) * pageSize >= items.value.length) page.value = 1
})
const q = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
  page.value = 1
  try {
    const r = await api.get('/admin/problems', { params: { q: q.value } }) as any
    items.value = r.items ?? []
  } finally {
    loading.value = false
  }
}

async function togglePublic(row: any, isPublic: boolean) {
  try {
    await api.put(`/admin/problems/${row.id}`, { is_public: isPublic })
    row.is_public = isPublic
    ElMessage.success(isPublic ? '已设为公开' : '已设为私有')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

onMounted(load)
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
:deep(.mono-id), .mono-id {
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
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { font-size: 26px; letter-spacing: -0.02em; }
.head-ops { display: flex; align-items: center; gap: var(--oj-s2); }
.head-sep { width: 1px; height: 20px; background: var(--oj-line); }
.pager-row {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0;
}
.preview {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: var(--oj-s3) var(--oj-s4);
}
</style>
