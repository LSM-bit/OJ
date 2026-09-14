<!--
  AdminTags.vue - 后台标签管理：全量标签实例列表（含未使用的孤儿标签）
  支持新增、搜索、重命名（同步替换所有题目 tags 数组中的旧名）、删除（从题目 tags 移除）
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索标签名" clearable style="width: 240px"
                @keyup.enter="load" @clear="load" />
      <el-button type="primary" @click="load">搜索</el-button>
      <div class="spacer" />
      <el-button type="primary" plain @click="openCreate">
        <el-icon style="margin-right:4px"><Plus /></el-icon>新建标签
      </el-button>
    </div>

    <el-table :data="items" v-loading="loading" height="calc(100vh - 160px)">
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
      <el-table-column label="使用题数" width="100">
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
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { api } from '../../api/client'

const items = ref<any[]>([])
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
  color: var(--el-text-color-secondary);
}
:deep(.mono-id), .mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
</style>
