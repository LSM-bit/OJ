<!--
  AdminTeams.vue - 后台团队管理：全量团队列表（队长/人数/创建时间）
-->
<template>
  <div class="page">
    <el-table :data="items" v-loading="loading" height="calc(100vh - 140px)">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="团队名" min-width="160" />
      <el-table-column prop="owner_name" label="队长" width="130" />
      <el-table-column prop="member_count" label="人数" width="80" />
      <el-table-column prop="description" label="简介" min-width="200" show-overflow-tooltip />
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../../api/client'

const items = ref<any[]>([])
const loading = ref(false)

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 16) : '')

async function load() {
  loading.value = true
  try {
    const r = await api.get('/admin/teams') as any
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
