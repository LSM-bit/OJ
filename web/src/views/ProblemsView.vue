<template>
  <div>
    <h2>题目列表</h2>
    <el-table :data="problems" v-loading="loading" stripe>
      <el-table-column prop="display_id" label="#" width="80" />
      <el-table-column prop="title" label="标题" min-width="240">
        <template #default="{ row }">
          <router-link :to="`/problems/${row.id}`" class="title-link">{{ row.title }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="difficulty" label="难度" width="100">
        <template #default="{ row }">
          <el-tag :type="diffTag(row.difficulty)" size="small">{{ diffLabel(row.difficulty) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="限制" width="160">
        <template #default="{ row }">{{ row.time_limit_ms }}ms / {{ row.memory_limit_mb }}MB</template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && problems.length === 0" description="暂无题目" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api/client'

const problems = ref<any[]>([])
const loading = ref(false)

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  loading.value = true
  try {
    problems.value = await api.get('/problems') as any
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.title-link { color: var(--el-color-primary); text-decoration: none; }
.title-link:hover { text-decoration: underline; }
</style>
