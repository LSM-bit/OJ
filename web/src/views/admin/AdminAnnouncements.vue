<!--
  AdminAnnouncements.vue - 后台公告管理：管理员发布/编辑/置顶/删除全站公告
  数据源复用前台只读接口 GET /misc/announcements（展示最近 50 条），写操作走 /misc/announcements*
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>公告管理</h2>
      </div>
      <div class="head-ops">
        <el-input v-model="q" placeholder="搜索标题/内容" clearable style="width: 240px" />
        <el-button type="primary" plain @click="openCreate">
          <el-icon style="margin-right:4px"><Plus /></el-icon>发布公告
        </el-button>
      </div>
    </header>
    <el-table :data="pagedFiltered" v-loading="loading" height="calc(100vh - 218px)">
      <el-table-column label="置顶" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.top" size="small" type="danger" effect="dark">置顶</el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="内容" min-width="280">
        <template #default="{ row }">
          <span class="preview">{{ (row.content || '').replace(/\s+/g, ' ').slice(0, 60) || '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发布时间" width="180">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="warning" @click="toggleTop(row)">
            {{ row.top ? '取消置顶' : '置顶' }}
          </el-button>
          <el-button size="small" text type="danger" @click="remove(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pager-row">
      <el-pagination v-if="filtered.length > pageSize" class="pager"
                     layout="total, prev, pager, next"
                     :total="filtered.length" :page-size="pageSize"
                     v-model:current-page="page" />
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑公告' : '发布公告'" width="620">
      <el-form label-position="top">
        <el-form-item label="标题">
          <el-input v-model="form.title" maxlength="128" show-word-limit placeholder="如：国庆赛报名开启" />
        </el-form-item>
        <el-form-item label="正文（展示在主页公告栏，详情弹窗中原样呈现）">
          <el-input v-model="form.content" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }"
                    maxlength="5000" show-word-limit placeholder="支持换行的纯文本" />
        </el-form-item>
        <el-form-item label="置顶">
          <el-switch v-model="form.top" />
          <span class="tip">置顶公告排在公告栏最前</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">
          {{ editing ? '保存' : '发布' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { api } from '../../api/client'

const items = ref<any[]>([])
const q = ref('')
const loading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editing = ref<any>(null)
const form = reactive({ title: '', content: '', top: false })

const filtered = computed(() => {
  const k = q.value.trim().toLowerCase()
  if (!k) return items.value
  return items.value.filter(
    (a) => (a.title || '').toLowerCase().includes(k) || (a.content || '').toLowerCase().includes(k))
})

// 客户端分页：公告只展示最近 50 条，页面内分页
const page = ref(1)
const pageSize = 20
const pagedFiltered = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch(q, () => { page.value = 1 })

async function load() {
  loading.value = true
  try {
    items.value = await api.get('/misc/announcements', { params: { limit: 50 } }) as any
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  form.title = ''
  form.content = ''
  form.top = false
  dialogVisible.value = true
}

function openEdit(row: any) {
  editing.value = row
  form.title = row.title
  form.content = row.content || ''
  form.top = !!row.top
  dialogVisible.value = true
}

async function save() {
  const title = form.title.trim()
  if (!title) return ElMessage.warning('请填写标题')
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/misc/announcements/${editing.value.id}`,
        { title, content: form.content, top: form.top })
      ElMessage.success('已保存')
    } else {
      await api.post('/misc/announcements', { title, content: form.content, top: form.top })
      ElMessage.success('公告已发布')
    }
    dialogVisible.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  } finally {
    saving.value = false
  }
}

async function toggleTop(row: any) {
  try {
    await api.put(`/misc/announcements/${row.id}`, { top: !row.top })
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

async function remove(row: any) {
  try {
    await ElMessageBox.confirm(`确定删除公告「${row.title}」？`, '删除公告', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.delete(`/misc/announcements/${row.id}`)
    ElMessage.success('已删除')
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
.muted { color: var(--oj-ink-4); }
.preview {
  font-size: 13px;
  color: var(--oj-ink-2);
}
.tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--oj-ink-3);
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
