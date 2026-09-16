<!--
  AdminAnnouncements.vue - 后台公告管理：管理员发布/编辑/置顶/删除全站公告
  数据源复用前台只读接口 GET /misc/announcements（展示最近 50 条），写操作走 /misc/announcements*
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索标题/内容" clearable style="width: 240px" />
      <div class="spacer" />
      <el-button type="primary" plain @click="openCreate">
        <el-icon style="margin-right:4px"><Plus /></el-icon>发布公告
      </el-button>
    </div>

    <el-table :data="filtered" v-loading="loading" height="calc(100vh - 160px)">
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
import { computed, onMounted, reactive, ref } from 'vue'
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
.muted { color: var(--el-text-color-placeholder); }
.preview {
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
