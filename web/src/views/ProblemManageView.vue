<!--
  ProblemManageView.vue - 出题中心（创作视角）
  与刷题列表（ProblemsView，只看公开题）分开：
  这里展示「我管理的题目」——自己的 + 团队的，含未公开草稿；
  可创建题目（三步向导）、继续编辑、发布/撤回；也是创建题单/比赛的入口
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>出题中心</h2>
      <div class="head-actions">
        <el-button size="small" @click="$router.push('/manage/playlists')">管理题单</el-button>
        <el-button size="small" @click="$router.push('/contests/new')">创建比赛</el-button>
        <el-button type="primary" size="small" @click="$router.push('/problems/new')">
          创建题目
        </el-button>
      </div>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="我的题目" name="problems">
        <el-table :data="problems" stripe class="fill-table" v-loading="loading">
          <el-table-column prop="display_id" label="题号" width="80" />
          <el-table-column prop="title" label="标题" min-width="220">
            <template #default="{ row }">
              <router-link :to="`/problems/${row.id}/edit`" class="title-link">
                {{ row.title }}
              </router-link>
            </template>
          </el-table-column>
          <el-table-column prop="difficulty" label="难度" width="90">
            <template #default="{ row }">
              <el-tag :type="diffTag(row.difficulty)" size="small">
                {{ diffLabel(row.difficulty) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_public ? 'success' : 'warning'" size="small" effect="light">
                {{ row.is_public ? '已公开' : '草稿' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <el-button size="small" text type="primary"
                         @click="$router.push(`/problems/${row.id}/edit`)">编辑</el-button>
              <el-button size="small" text @click="$router.push(`/problems/${row.id}`)">预览</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && problems.length === 0"
                  description="还没有题目，点右上角「创建题目」开始出题" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
// 出题中心：mine=1 拉取我管理的题目（含草稿）
import { onMounted, ref } from 'vue'
import { api } from '../api/client'

const problems = ref<any[]>([])
const loading = ref(false)
const tab = ref('problems')

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  loading.value = true
  try {
    problems.value = await api.get('/problems?mine=1') as any
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.head-actions { display: flex; gap: 8px; }
.fill-table { width: 100%; }
.title-link { color: var(--el-color-primary); text-decoration: none; }
.title-link:hover { text-decoration: underline; }
</style>
