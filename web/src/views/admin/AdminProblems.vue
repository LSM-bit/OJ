<!--
  AdminProblems.vue - 后台题目管理：全量列表（含私有）+ 公开性切换
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索题目标题" clearable style="width: 240px"
                @keyup.enter="load" @clear="load" />
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table :data="items" v-loading="loading" height="calc(100vh - 160px)">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="display_id" label="题号" width="70" />
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
      <el-table-column prop="case_count" label="测试点" width="80" />
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'

const items = ref<any[]>([])
const q = ref('')
const loading = ref(false)

async function load() {
  loading.value = true
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
</style>
