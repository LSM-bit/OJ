<template>
  <div v-loading="loading" class="page">
    <div class="page-head">
      <h2>题目列表</h2>
      <div class="head-actions">
        <el-button v-if="userStore.isLoggedIn" size="small"
                   @click="$router.push('/manage')">去出题</el-button>
      </div>
    </div>

    <div class="body-grid">
      <!-- 左侧栏：公告栏 + 题号跳转 -->
      <div class="side-col">
        <!-- 公告栏 -->
        <div class="announce-panel">
          <div class="panel-head">
            <span class="panel-title">📢 公告</span>
            <el-tag v-if="announcements.length" size="small" effect="plain" type="info">
              {{ announcements.length }} 条
            </el-tag>
          </div>
          <div class="announce-list">
            <div v-for="a in announcements" :key="a.id" class="announce-item"
                 @click="viewAnnounce(a)">
              <div class="announce-item-title">
                <el-tag v-if="a.top" type="danger" size="small" effect="dark">置顶</el-tag>
                {{ a.title }}
              </div>
              <div class="announce-item-date">{{ (a.created_at || '').slice(0, 10) }}</div>
            </div>
            <el-empty v-if="!loadingAnn && announcements.length === 0" description="暂无公告"
                      :image-size="60" />
          </div>
        </div>

        <!-- 题号跳转（大） -->
        <div class="jump-panel">
          <div class="panel-head">
            <span class="panel-title">🎯 题目跳转</span>
          </div>
          <div class="jump-body">
            <el-input v-model="jumpId" size="large" placeholder="输入题号，如 3"
                      @keyup.enter="jump" clearable>
              <template #prepend>#</template>
            </el-input>
            <div class="jump-btns">
              <el-button type="primary" @click="jump" class="jump-btn">跳转</el-button>
              <el-button type="success" plain :disabled="problems.length === 0"
                         @click="randomJump" class="jump-btn">随机一题</el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右：题目表 -->
      <div class="table-panel">
        <el-table :data="problems" stripe class="fill-table">
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
    </div>

    <!-- 公告详情弹窗 -->
    <el-dialog v-model="showAnn" :title="currentAnn?.title" width="520">
      <div class="ann-meta">
        <el-tag v-if="currentAnn?.top" type="danger" size="small" effect="dark">置顶</el-tag>
        <span>{{ (currentAnn?.created_at || '').slice(0, 16).replace('T', ' ') }}</span>
      </div>
      <div class="ann-content markdown" v-html="renderedAnn"></div>
      <template #footer>
        <el-button @click="showAnn = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 主页（题目列表）：刷题视角，只展示公开题目；左侧公告栏 + 题号跳转/随机一题
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'
import md from '../utils/markdown'

const router = useRouter()
const userStore = useUserStore()
const problems = ref<any[]>([])
const loading = ref(false)
const jumpId = ref('')

// 公告栏
const announcements = ref<any[]>([])
const loadingAnn = ref(false)
const showAnn = ref(false)
const currentAnn = ref<any>(null)
const renderedAnn = computed(() =>
  currentAnn.value ? md.render(currentAnn.value.content ?? '') : '')

function viewAnnounce(a: any) {
  currentAnn.value = a
  showAnn.value = true
}

// 指定题号跳转：在已加载的公开题目中找 display_id
function jump() {
  const n = Number(jumpId.value)
  if (!jumpId.value.trim() || Number.isNaN(n)) {
    ElMessage.warning('请输入题号')
    return
  }
  const p = problems.value.find((x) => x.display_id === n)
  if (!p) {
    ElMessage.warning(`题号 #${n} 不存在或未公开`)
    return
  }
  router.push(`/problems/${p.id}`)
}

// 随机一题：等概率取一道公开题
function randomJump() {
  if (problems.value.length === 0) return
  const p = problems.value[Math.floor(Math.random() * problems.value.length)]
  router.push(`/problems/${p.id}`)
}

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  loading.value = true
  loadingAnn.value = true
  try {
    problems.value = await api.get('/problems') as any
  } finally {
    loading.value = false
  }
  try {
    announcements.value = await api.get('/misc/announcements') as any
  } catch { /* 公告加载失败不阻塞列表 */ } finally {
    loadingAnn.value = false
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
  margin-bottom: 12px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 左侧栏（公告 + 跳转） + 右题目表 */
.body-grid {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
/* 左侧栏悬浮：页面滚动时跟随视口（top 留出页面内边距） */
.side-col {
  flex: 0 0 300px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: sticky;
  top: 16px;
  align-self: flex-start;
}
.announce-panel,
.jump-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-color-primary-light-9);
}
.panel-title { font-weight: 700; font-size: 14px; }
/* 公告栏加长：占满视口剩余高度（跳转面板固定高度，公告吃掉剩余空间） */
.announce-panel {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 300px);
  min-height: 320px;
}
.announce-list {
  flex: 1;
  overflow-y: auto;
}
.announce-item {
  padding: 10px 14px;
  border-bottom: 1px dashed var(--el-border-color-lighter);
  cursor: pointer;
}
.announce-item:last-child { border-bottom: none; }
.announce-item:hover { background: var(--el-fill-color-light); }
.announce-item-title {
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  word-break: break-all;
}
.announce-item-date {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  flex-shrink: 0;
}

/* 题号跳转（大输入框 + 大按钮） */
.jump-panel { flex-shrink: 0; }
.jump-body {
  padding: 14px;
}
.jump-body :deep(.el-input__wrapper) {
  border-radius: 6px;
}
.jump-btns {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}
.jump-btn {
  flex: 1;
  height: 40px;
  font-size: 15px;
}
.table-panel { flex: 1; min-width: 0; }
.fill-table {
  width: 100%;
}
.title-link { color: var(--el-color-primary); text-decoration: none; }
.title-link:hover { text-decoration: underline; }

/* 公告详情弹窗 */
.ann-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}
.ann-content { max-height: 50vh; overflow-y: auto; }
</style>
