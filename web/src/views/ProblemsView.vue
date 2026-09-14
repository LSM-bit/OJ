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
        <!-- 搜索行：标题关键词（回车/清空即搜） -->
        <div class="search-row">
          <el-input v-model="keyword" placeholder="搜索题目标题 / 题号" clearable
                    :prefix-icon="Search" class="kw-input"
                    @keyup.enter="doSearch" @clear="doSearch" />
          <el-button type="primary" @click="doSearch">搜索</el-button>
        </div>
        <!-- 标签筛选：候选列表默认收起，点击搜索框展开、点击外部收起（下拉式）；
             模糊过滤 + 点击行选中，多标签取交集，选中状态同步到 URL ?tag= -->
        <div v-if="tagCloud.length" ref="tagFilterRef" class="tag-filter">
          <el-input v-model="tagSearch" placeholder="点击搜索标签" clearable
                    :prefix-icon="Search" @focus="listVisible = true" />
          <div v-if="selectedTags.size" class="picked-row">
            <span class="picked-label">已选 {{ selectedTags.size }}：</span>
            <el-tag v-for="t in [...selectedTags]" :key="t" size="small" closable
                    @close="toggleTag(t)">{{ t }}</el-tag>
            <el-button link type="danger" size="small" class="clear-btn" @click="clearTags">
              清除筛选
            </el-button>
          </div>
          <div v-show="listVisible" class="tag-list">
            <div v-for="t in visibleTags" :key="t.tag" class="tag-row"
                 :class="{ picked: selectedTags.has(t.tag) }" @click="toggleTag(t.tag)">
              <span class="tag-name">{{ t.tag }}</span>
              <span class="tag-meta">
                <span class="tag-count">{{ t.count }} 题</span>
                <el-icon v-if="selectedTags.has(t.tag)" class="check"><Check /></el-icon>
              </span>
            </div>
            <div v-if="!visibleTags.length" class="no-tag empty">无匹配标签</div>
          </div>
        </div>
        <el-table :data="problems" stripe class="fill-table">
          <el-table-column prop="display_id" label="#" width="80" />
          <el-table-column prop="title" label="标题" min-width="200">
            <template #default="{ row }">
              <router-link :to="`/problems/${row.id}`" class="title-link">{{ row.title }}</router-link>
            </template>
          </el-table-column>
          <el-table-column label="标签" min-width="160">
            <template #default="{ row }">
              <template v-if="row.tags && row.tags.length">
                <el-tag v-for="t in row.tags.slice(0, 3)" :key="t" size="small" effect="plain"
                        class="row-tag" @click="toggleTag(t)">{{ t }}</el-tag>
                <el-tooltip v-if="row.tags.length > 3" :content="row.tags.slice(3).join('、')"
                            placement="top">
                  <el-tag size="small" effect="plain" type="info" class="row-tag">
                    +{{ row.tags.length - 3 }}
                  </el-tag>
                </el-tooltip>
              </template>
              <span v-else class="no-tag">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="difficulty" label="难度" width="90">
            <template #default="{ row }">
              <el-tag :type="diffTag(row.difficulty)" size="small">{{ diffLabel(row.difficulty) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="限制" width="150">
            <template #default="{ row }">{{ row.time_limit_ms }}ms / {{ row.memory_limit_mb }}MB</template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && problems.length === 0"
                  :description="selectedTags.size ? '没有符合所选标签的题目' : '暂无题目'" />
        <!-- 分页：full=1 拿 {total, items}，任意页都能翻到 -->
        <el-pagination v-if="total > pageSize" class="pager" layout="total, prev, pager, next, jumper"
                       :total="total" :page-size="pageSize" :current-page="page"
                       @current-change="(p: number) => { page = p; loadProblems() }" />
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
// 标签筛选：标签云来自 GET /problems/tags，点击标签带 ?tag= 重新拉列表（多标签交集）
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Check } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'
import md from '../utils/markdown'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const problems = ref<any[]>([])
const loading = ref(false)
const jumpId = ref('')

// 分页 + 关键词搜索（后端 GET /problems?full=1&page=&size=&q=&tag= → {total, items}）
const keyword = ref((typeof route.query.q === 'string' ? route.query.q : ''))
const page = ref(1)
const pageSize = 50
const total = ref(0)

// 标签云与已选标签（Set 保证多选去重）
const tagCloud = ref<{ tag: string; count: number }[]>([])
const selectedTags = reactive(new Set<string>())

// 标签筛选（下拉式）：候选列表默认收起，点击搜索框展开、点外部收起；搜索框模糊过滤
const tagSearch = ref('')
const listVisible = ref(false)
const tagFilterRef = ref<HTMLElement | null>(null)

// 点击区域外收起下拉列表
function onDocClick(e: MouseEvent) {
  if (tagFilterRef.value && !tagFilterRef.value.contains(e.target as Node)) {
    listVisible.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

// 点击标签行：切换选中状态并重新加载列表（多标签 = 交集）；筛选变了回第 1 页
async function toggleTag(tag: string) {
  if (selectedTags.has(tag)) selectedTags.delete(tag)
  else selectedTags.add(tag)
  page.value = 1
  await loadProblems()
}

// 搜索框模糊过滤标签（大小写不敏感），已选项始终保留在结果里
const visibleTags = computed(() => {
  const kw = tagSearch.value.trim().toLowerCase()
  if (!kw) return tagCloud.value
  return tagCloud.value.filter((t) => t.tag.toLowerCase().includes(kw)
    || selectedTags.has(t.tag))
})

function clearTags() {
  selectedTags.clear()
  page.value = 1
  loadProblems()
}

// 关键词搜索（标题模糊 / 纯数字同时主题号）：回到第 1 页再拉
function doSearch() {
  page.value = 1
  loadProblems()
}

async function loadProblems() {
  loading.value = true
  try {
    const params: Record<string, any> = { full: 1, page: page.value, size: pageSize }
    if (selectedTags.size) params.tag = [...selectedTags].join(',')
    const kw = keyword.value.trim()
    if (kw) params.q = kw
    // 筛选/搜索状态同步进 URL（前进/后退、分享链接都能还原）
    router.replace({ query: { ...route.query,
      tag: selectedTags.size ? [...selectedTags].join(',') : undefined,
      q: kw || undefined } })
    const r = await api.get('/problems', { params }) as any
    problems.value = r.items ?? []
    total.value = r.total ?? 0
  } finally {
    loading.value = false
  }
}

// 题目详情页点标签跳回列表：读取 ?tag= 预选（仅首次加载解析，之后以页面内操作为准）
const routeTag = computed(() => (typeof route.query.tag === 'string' ? route.query.tag : ''))
routeTag.value.split(',').map((s) => s.trim()).filter(Boolean).forEach((t) => selectedTags.add(t))

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

// 指定题号跳转：走后端 did= 精确查（不受当前分页限制，全库任意题号可达）
async function jump() {
  const n = Number(jumpId.value)
  if (!jumpId.value.trim() || Number.isNaN(n)) {
    ElMessage.warning('请输入题号')
    return
  }
  try {
    const r = await api.get('/problems', { params: { full: 1, did: n } }) as any
    const p = (r.items ?? [])[0]
    if (!p) {
      ElMessage.warning(`题号 #${n} 不存在或未公开`)
      return
    }
    router.push(`/problems/${p.id}`)
  } catch {
    ElMessage.error('查询失败，请稍后再试')
  }
}

// 随机一题：在当前筛选视角内取最大公开题号，随机 did 逐个试跳（题号有空洞，最多试 20 次）
async function randomJump() {
  if (total.value === 0) return
  let maxDid = 0
  try {
    // 列表按题号升序：offset = total-1 的那条即当前视角最大公开题号（page=total, size=1）
    const r0 = await api.get('/problems', { params: { full: 1, page: total.value, size: 1,
      tag: selectedTags.size ? [...selectedTags].join(',') : undefined,
      q: keyword.value.trim() || undefined } }) as any
    maxDid = (r0.items ?? [])[0]?.display_id ?? 0
  } catch { /* ignore */ }
  if (!maxDid) return
  // 随机候选也遵循当前标签/关键词筛选
  const filter: Record<string, any> = {
    full: 1,
    tag: selectedTags.size ? [...selectedTags].join(',') : undefined,
    q: keyword.value.trim() || undefined }
  for (let i = 0; i < 20; i++) {
    const n = 1 + Math.floor(Math.random() * maxDid)
    try {
      const r = await api.get('/problems', { params: { ...filter, did: n } }) as any
      const p = (r.items ?? [])[0]
      if (p) {
        router.push(`/problems/${p.id}`)
        return
      }
    } catch { /* ignore，继续试下一个 */ }
  }
  ElMessage.warning('随机选题失败，请重试')
}

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  await loadProblems()
  // 公告与标签云加载失败不阻塞列表展示
  try {
    announcements.value = await api.get('/misc/announcements') as any
  } catch { /* ignore */ } finally {
    loadingAnn.value = false
  }
  try {
    tagCloud.value = (await api.get('/problems/tags') as any).items ?? []
  } catch { /* ignore */ }
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
/* 搜索行 + 分页条 */
.search-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.kw-input { max-width: 320px; }
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
.fill-table {
  width: 100%;
}
.title-link { color: var(--el-color-primary); text-decoration: none; }
.title-link:hover { text-decoration: underline; }

/* 标签筛选（搜索框 + 可展开的下拉候选列表） */
.tag-filter { margin-bottom: 10px; }
.picked-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.picked-label { font-size: 13px; color: var(--el-text-color-secondary); }
.clear-btn { margin-left: 4px; }
.tag-list {
  margin-top: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  max-height: 240px;
  overflow-y: auto;
}
.tag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  font-size: 13px;
  cursor: pointer;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.tag-row:last-child { border-bottom: none; }
.tag-row:hover { background: var(--el-fill-color-light); }
.tag-row.picked { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.tag-name { word-break: break-all; }
.tag-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.tag-count { font-size: 12px; color: var(--el-text-color-placeholder); }
.check { color: var(--el-color-primary); }
.empty { padding: 16px 0; text-align: center; }
.no-tag { color: var(--el-text-color-placeholder); font-size: 13px; }
.row-tag { cursor: pointer; margin-right: 4px; }

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
