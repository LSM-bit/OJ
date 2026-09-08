<!--
  AdminPlaylists.vue - 后台题单管理：全量题单列表（含私有）
-->
<template>
  <div class="page">
    <el-table :data="items" v-loading="loading" height="calc(100vh - 140px)">
      <el-table-column label="ID" width="130">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ shortId(row.id) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="200" />
      <el-table-column label="可见性" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_public ? 'success' : 'danger'">
            {{ row.is_public ? '公开' : '私有' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="归属" width="130">
        <template #default="{ row }">
          <span :title="row.owner_id">
            {{ row.owner_type === 'team' ? `团队#${shortId(row.owner_id)}` : `用户#${shortId(row.owner_id)}` }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button size="small" text @click="$router.push(`/playlists/${row.id}`)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'
import { shortId } from '../../utils/format'

const items = ref<any[]>([])
const loading = ref(false)

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 16) : '')

async function load() {
  loading.value = true
  try {
    const r = await api.get('/admin/playlists') as any
    items.value = r.items ?? []
  } finally {
    loading.value = false
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
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
</style>
