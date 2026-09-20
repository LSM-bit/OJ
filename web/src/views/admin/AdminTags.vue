<!--
  AdminTags.vue - 后台标签管理：全量标签实例列表（含未使用的孤儿标签）
  支持新增、搜索、重命名（同步替换所有题目 tags 数组中的旧名）、删除（从题目 tags 移除）
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>标签管理</h2>
      </div>
      <div class="head-ops">
        <el-input v-model="q" placeholder="搜索标签名" clearable style="width: 220px"
                  @keyup.enter="load" @clear="load" />
        <el-button type="primary" @click="load">搜索</el-button>
        <span class="head-sep" />
        <el-button type="primary" plain @click="openCreate">
          <el-icon style="margin-right:4px"><Plus /></el-icon>新建标签
        </el-button>
      </div>
    </header>

    <el-table :data="pagedItems" v-loading="loading" height="calc(100dvh - 218px)">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="标签名" min-width="160">
        <template #default="{ row }">
          <el-tag size="small">{{ row.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="使用题数" width="100" align="right">
        <template #default="{ row }">
          <el-tag size="small" :type="row.problem_count > 0 ? 'success' : 'info'">
            {{ row.problem_count }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">
          {{ formatTime(row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openRename(row)">重命名</el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager-row">
      <el-pagination v-if="items.length > pageSize" class="pager"
                     layout="total, prev, pager, next"
                     :total="items.length" :page-size="pageSize"
                     v-model:current-page="page" />
    </div>

    <el-dialog v-model="createVisible" title="新建标签" width="420">
      <el-input v-model="createName" maxlength="32" show-word-limit
                placeholder="标签名，如：动态规划 / 贪心" @keyup.enter="doCreate" />
      <div class="rename-tip">新建后可在出题表单的标签弹窗中被搜索和选择。</div>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" @click="doCreate">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="renameVisible" title="重命名标签" width="420">
      <el-input v-model="renameName" maxlength="32" show-word-limit
                @keyup.enter="doRename" />
      <div class="rename-tip">
        将同步替换所有题目上的旧标签名，当前 {{ current?.problem_count ?? 0 }} 道题在使用。
      </div>
      <template #footer>
        <el-button @click="renameVisible = false">取消</el-button>
        <el-button type="primary" @click="doRename">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
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

// 新建 / 重命名弹窗状态
const createVisible = ref(false)
const createName = ref('')
const renameVisible = ref(false)
const renameName = ref('')
const current = ref<any>(null)

async function load() {
  loading.value = true
  page.value = 1
  try {
    const r = await api.get('/admin/tags', { params: { q: q.value } }) as any
    items.value = r.items ?? []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createName.value = ''
  createVisible.value = true
}

async function doCreate() {
  const name = createName.value.trim()
  if (!name) return
  try {
    await api.post('/admin/tags', { name })
    ElMessage.success(`已创建标签「${name}」`)
    createVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  }
}

function openRename(row: any) {
  current.value = row
  renameName.value = row.name
  renameVisible.value = true
}

async function doRename() {
  const name = renameName.value.trim()
  if (!name || !current.value) return
  try {
    const r = await api.put(`/admin/tags/${current.value.id}`, { name }) as any
    ElMessage.success(r.touched ? `已重命名，同步更新 ${r.touched} 道题目` : '已重命名')
    renameVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '重命名失败')
  }
}

async function remove(row: any) {
  const tip = row.problem_count > 0
    ? `有 ${row.problem_count} 道题正在使用标签「${row.name}」，删除后将从这些题目的标签中移除，确定删除？`
    : `确定删除标签「${row.name}」？`
  try {
    await ElMessageBox.confirm(tip, '删除标签', { type: 'warning' })
  } catch {
    return
  }
  try {
    const r = await api.delete(`/admin/tags/${row.id}`) as any
    ElMessage.success(r.touched ? `已删除，从 ${r.touched} 道题目移除` : '已删除')
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '删除失败')
  }
}

function formatTime(s: string) {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 16)
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
.spacer { flex: 1; }
.rename-tip {
  margin-top: 8px;
  font-size: 12px;
  color: var(--oj-ink-3);
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
