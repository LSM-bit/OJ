<template>
  <div v-loading="loading" class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Problems</span>
        <h2>题库</h2>
      </div>
      <el-button v-if="userStore.isLoggedIn" size="small" @click="$router.push('/manage')">
        创建题目
      </el-button>
    </header>

    <div class="table-panel">
      <!-- 工具行：搜索题目 / 搜索标签 / 题目跳转，三者同行；点击标签框展开候选、点外部收起 -->
      <div ref="tagFilterRef" class="tool-block">
        <div class="tool-row">
          <!-- 搜索题目：标题关键词（回车 / 清空即搜） -->
          <div class="tool-cell">
            <div class="tool-line">
              <el-input v-model="keyword" placeholder="搜索题目标题 / 题号" clearable
                        :prefix-icon="Search" @keyup.enter="doSearch" @clear="doSearch" />
              <el-button type="primary" @click="doSearch">搜索</el-button>
            </div>
          </div>

          <!-- 搜索标签：点击展开候选，模糊过滤 + 点击行选中，多标签取交集 -->
          <div v-if="tagCloud.length" class="tool-cell">
            <el-input v-model="tagSearch" placeholder="点击搜索标签" clearable
                      :prefix-icon="Search" @focus="listVisible = true" />
          </div>

          <!-- 题目跳转：按题号精确跳（全库可达），或当前筛选内随机一题 -->
          <div class="tool-cell jump-cell">
            <el-input v-model="jumpId" placeholder="输入题号，如 3" @keyup.enter="jump" clearable>
              <template #prepend>#</template>
            </el-input>
            <el-button type="primary" @click="jump">跳转</el-button>
            <el-button plain :disabled="problems.length === 0" @click="randomJump">随机一题</el-button>
          </div>
        </div>

        <!-- 标签候选：展开于工具行下方 -->
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

        <!-- 已选标签：多标签取交集 -->
        <div v-if="selectedTags.size" class="picked-row">
          <span class="picked-label">已选 {{ selectedTags.size }}：</span>
          <el-tag v-for="t in [...selectedTags]" :key="t" size="small" closable
                  @close="toggleTag(t)">{{ t }}</el-tag>
          <el-button link type="danger" size="small" class="clear-btn" @click="clearTags">
            清除筛选
          </el-button>
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
</template>

<script setup lang="ts">
// 题库页：刷题视角，只展示公开题目；搜索题目 / 搜索标签 / 题号跳转同处一行
// 标签筛选：标签云来自 GET /problems/tags，点击标签带 ?tag= 重新拉列表（多标签交集）
// 公告已上移到全局顶栏入口（App.vue），本页不再承载公告
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Search, Check } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

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
  // 标签云加载失败不阻塞列表展示
  try {
    tagCloud.value = (await api.get('/problems/tags') as any).items ?? []
  } catch { /* ignore */ }
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
  overflow-y: auto;
}

/* 页头：小标 + 主标题，右侧主行动，底部一条细线压住版面 */
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s4);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { font-size: 26px; letter-spacing: -0.02em; }

/* 工具 + 表格同处一块版面 */
.table-panel {
  min-width: 0;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  padding: var(--oj-s4) var(--oj-s4) var(--oj-s3);
}

/* 工具行：搜索题目 / 搜索标签 / 题目跳转 —— 三块同行，窄屏自动折行 */
.tool-block { margin-bottom: var(--oj-s3); }
.tool-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line-soft);
}
.tool-cell { flex: 1 1 240px; min-width: 0; }
.tool-line { display: flex; gap: var(--oj-s2); }
.jump-cell { display: flex; gap: var(--oj-s2); }
.jump-cell :deep(.el-input) { flex: 1; min-width: 0; }

/* 标签候选：展开于工具行下方（内联块，超高滚动） */
.tag-list {
  margin-top: var(--oj-s2);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
  background: var(--oj-surface);
  max-height: 240px;
  overflow-y: auto;
}
.tag-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 7px 12px;
  font-size: var(--oj-fs-sm);
  cursor: pointer;
  border-bottom: 1px solid var(--oj-line-soft);
  transition: background-color var(--oj-dur-1) var(--oj-ease);
}
.tag-row:last-child { border-bottom: none; }
.tag-row:hover { background: var(--oj-surface-2); }
.tag-row.picked {
  background: var(--oj-accent-soft);
  color: var(--oj-accent);
  font-weight: 500;
}
.tag-name { word-break: break-all; }
.tag-meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.tag-count {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  color: var(--oj-ink-4);
}
.check { color: var(--oj-accent); }
.empty { padding: 16px 0; text-align: center; }
.no-tag { color: var(--oj-ink-4); font-size: var(--oj-fs-sm); }

/* 已选标签行 */
.picked-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: var(--oj-s2);
}
.picked-label { font-size: var(--oj-fs-sm); color: var(--oj-ink-3); }
.clear-btn { margin-left: 4px; }

.fill-table { width: 100%; }
.title-link {
  font-weight: 500;
  color: var(--oj-ink);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color var(--oj-dur-1) var(--oj-ease),
              border-color var(--oj-dur-1) var(--oj-ease);
}
.title-link:hover { color: var(--oj-accent); border-bottom-color: var(--oj-accent); }
.pager { margin-top: var(--oj-s4); justify-content: flex-end; }
.row-tag { cursor: pointer; margin-right: 4px; }
</style>
