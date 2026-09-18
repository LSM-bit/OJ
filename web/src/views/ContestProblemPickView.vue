<!--
  ContestProblemPickView.vue - 创建比赛第二步：选择比赛题目（独立页面）
  基本信息在第一步（ContestEditView）填好，草稿存 sessionStorage(contest_new_draft)，
  本页负责挑题：支持「公开题目 / 我的题目」两个视角、标签多选筛选（交集）、
  题号或标题关键词搜索、分页浏览；已选题目按 A/B/C 顺序排列，可移除；
  确认后携带 problem_ids 调 POST /contests 完成创建。
-->
<template>
  <div class="page">
    <div class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Contest · Step 2</span>
        <h2>创建比赛 · 第 2 步：选择题目</h2>
      </div>
      <div class="head-actions">
        <el-tag v-if="draftTitle" size="small" effect="plain">比赛：{{ draftTitle }}</el-tag>
        <el-button size="small" @click="$router.push('/contests')">取消</el-button>
      </div>
    </div>

    <!-- 步骤条 -->
    <el-steps :active="2" align-center class="steps">
      <el-step title="基本信息" />
      <el-step title="选择题目" />
    </el-steps>

    <div class="pick-grid">
      <!-- 左：候选题目（可筛选/搜索/翻页） -->
      <div class="cand-panel">
        <el-tabs v-model="view" @tab-change="doSearch">
          <el-tab-pane label="公开题目" name="public" />
          <el-tab-pane label="我的题目（含草稿）" name="mine" />
        </el-tabs>
        <div class="filter-row">
          <el-input v-model="keyword" placeholder="搜索题号 / 标题" clearable
                    :prefix-icon="Search" class="kw-input"
                    @keyup.enter="doSearch" @clear="doSearch" />
          <el-button class="tag-filter-btn" @click="tagDialogVisible = true">
            <el-icon style="margin-right:4px"><Filter /></el-icon>
            标签筛选
            <span v-if="selTags.length" class="tag-count">{{ selTags.length }}</span>
          </el-button>
          <el-button v-if="selTags.length" link type="primary" @click="clearTags">清除</el-button>
        </div>

        <div v-if="selTags.length" class="picked-tags">
          <el-tag v-for="t in selTags" :key="t" size="small" closable @close="removeTag(t)">
            {{ t }}
          </el-tag>
        </div>

        <!-- 标签筛选弹窗：标签云多选 -->
        <el-dialog v-model="tagDialogVisible" title="按标签筛选" width="580" align-center>
          <el-input v-model="tagKeyword" placeholder="搜索标签" clearable class="tag-search" />
          <div class="tag-cloud-box">
            <el-check-tag v-for="t in filteredTagCloud" :key="t.tag"
                          :checked="selTags.includes(t.tag)"
                          @change="toggleTag(t.tag)">
              {{ t.tag }} <span class="tag-n">{{ t.count }}</span>
            </el-check-tag>
            <el-empty v-if="!filteredTagCloud.length" description="无匹配标签" :image-size="60" />
          </div>
          <template #footer>
            <el-button @click="clearTags">清空</el-button>
            <el-button @click="tagDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="applyTags">确定</el-button>
          </template>
        </el-dialog>
        <el-table :data="problems" size="small" v-loading="loading" class="fill-table">
          <el-table-column prop="display_id" label="#" width="70" />
          <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
          <el-table-column label="标签" min-width="140">
            <template #default="{ row }">
              <template v-if="row.tags && row.tags.length">
                <el-tag v-for="t in row.tags.slice(0, 2)" :key="t" size="small" effect="plain"
                        class="row-tag">{{ t }}</el-tag>
                <el-tooltip v-if="row.tags.length > 2" :content="row.tags.slice(2).join('、')"
                            placement="top">
                  <el-tag size="small" effect="plain" type="info" class="row-tag">
                    +{{ row.tags.length - 2 }}
                  </el-tag>
                </el-tooltip>
              </template>
              <span v-else class="no-tag">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="difficulty" label="难度" width="80">
            <template #default="{ row }">
              <el-tag :type="diffTag(row.difficulty)" size="small">{{ diffLabel(row.difficulty) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="90">
            <template #default="{ row }">
              <el-button v-if="!isPicked(row)" size="small" text type="primary"
                         @click="addProblem(row)">添加</el-button>
              <el-button v-else size="small" text type="info" disabled>已添加</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && problems.length === 0"
                  description="没有符合条件的题目" :image-size="60" />
        <el-pagination v-if="total > pageSize" class="pager" layout="total, prev, pager, next, jumper"
                       :total="total" :page-size="pageSize" :current-page="page"
                       @current-change="(p: number) => { page = p; loadProblems() }" />
      </div>

      <!-- 右：已选题目（A/B/C 顺序） -->
      <div class="picked-panel">
        <div class="panel-head">
          <span class="panel-title">已选 {{ picked.length }} 题</span>
          <el-button v-if="picked.length" link type="danger" size="small" @click="picked = []">
            清空
          </el-button>
        </div>
        <el-table :data="pagedPicked" size="small">
          <el-table-column label="题号" width="60">
            <template #default="{ $index }">{{ String.fromCharCode(65 + pickedOffset + $index) }}</template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
          <el-table-column label="操作" width="70">
            <template #default="{ $index }">
              <el-button size="small" text type="danger" @click="picked.splice(pickedOffset + $index, 1)">
                移除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="pickedTotal > pickedPageSize" class="pager-row">
          <el-pagination class="pager" layout="total, prev, pager, next"
                         :total="pickedTotal" :page-size="pickedPageSize"
                         v-model:current-page="pickedPage" />
        </div>
        <div v-if="!picked.length" class="pick-hint">
          暂未添加题目；也可以直接创建比赛，之后在管理页配置
        </div>
        <div class="foot-btns">
          <el-button @click="backToFirst">上一步</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">创建比赛</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 第二步页：从 sessionStorage 读第一步草稿；候选题 = 公开题 +（切 tab）我管理的题；
// 标签/关键词/分页全部走后端 GET /problems?full=1；创建时 problem_ids 按已选顺序（A/B/C）
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { Filter, Search } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useClientPager } from '../composables/useClientPager'

const router = useRouter()

const DRAFT_KEY = 'contest_new_draft'
const draft = ref<any>(null)
const draftTitle = computed(() => draft.value?.title ?? '')

// 候选列表状态
const view = ref<'public' | 'mine'>('public')
const problems = ref<any[]>([])
const loading = ref(false)
const keyword = ref('')
const selTags = ref<string[]>([])
const tagCloud = ref<{ tag: string; count: number }[]>([])
const page = ref(1)
const pageSize = 10
const total = ref(0)

// 已选题目（保持添加顺序 = 比赛 A/B/C 题号顺序；雪花 ID 用字符串）
const picked = ref<any[]>([])

// 已选题目可能很多：预留分页（题号字母按绝对序号推算）
const { page: pickedPage, size: pickedPageSize, total: pickedTotal, paged: pagedPicked } =
  useClientPager(computed<any[]>(() => picked.value), 20)
const pickedOffset = computed(() => (pickedPage.value - 1) * pickedPageSize.value)
const submitting = ref(false)

const isPicked = (row: any) => picked.value.some((x) => x.id === row.id)
function addProblem(row: any) {
  if (!isPicked(row)) picked.value.push(row)
}

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

function doSearch() {
  page.value = 1
  loadProblems()
}

// 标签筛选弹窗（标签云可能很长，独立弹窗内多选）
const tagDialogVisible = ref(false)
const tagKeyword = ref('')
const filteredTagCloud = computed(() => {
  const k = tagKeyword.value.trim().toLowerCase()
  if (!k) return tagCloud.value
  return tagCloud.value.filter((t) => t.tag.toLowerCase().includes(k))
})
function toggleTag(tag: string) {
  selTags.value = selTags.value.includes(tag)
    ? selTags.value.filter((t) => t !== tag)
    : [...selTags.value, tag]
}
function removeTag(tag: string) {
  selTags.value = selTags.value.filter((t) => t !== tag)
  doSearch()
}
function clearTags() {
  selTags.value = []
  doSearch()
}
function applyTags() {
  tagDialogVisible.value = false
  doSearch()
}

async function loadProblems() {
  loading.value = true
  try {
    const params: Record<string, any> = { full: 1, page: page.value, size: pageSize }
    if (view.value === 'mine') params.mine = 1
    if (selTags.value.length) params.tag = selTags.value.join(',')
    const kw = keyword.value.trim()
    if (kw) params.q = kw
    const r = await api.get('/problems', { params }) as any
    problems.value = r.items ?? []
    total.value = r.total ?? 0
  } finally {
    loading.value = false
  }
}

function backToFirst() {
  // 草稿仍在 sessionStorage，第一步页会原样恢复
  router.push('/contests/new')
}

async function submit() {
  if (!draft.value) {
    ElMessage.warning('未找到第一步填写的信息，请重新创建')
    router.replace('/contests/new')
    return
  }
  submitting.value = true
  try {
    const body: any = {
      title: draft.value.title.trim(),
      description: draft.value.description,
      rule: draft.value.rule,
      // value-format 含秒的本地时间串；Date 构造按本地时区解析，转真正的 UTC ISO
      start_at: new Date(draft.value.start_at).toISOString(),
      end_at: new Date(draft.value.end_at).toISOString(),
      board_freeze_minutes: draft.value.board_freeze_minutes,
      owner_type: draft.value.owner_type,
      is_public: draft.value.is_public,
      problem_ids: picked.value.map((p) => p.id),
    }
    if (draft.value.owner_type === 'team') body.team_id = draft.value.team_id
    const created: any = await api.post('/contests', body)
    sessionStorage.removeItem(DRAFT_KEY)
    ElMessage.success('比赛已创建')
    router.replace(`/contests/${created.id}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  const raw = sessionStorage.getItem(DRAFT_KEY)
  if (!raw) {
    ElMessage.warning('请先填写比赛基本信息')
    router.replace('/contests/new')
    return
  }
  try {
    draft.value = JSON.parse(raw)
  } catch {
    sessionStorage.removeItem(DRAFT_KEY)
    router.replace('/contests/new')
    return
  }
  loadProblems()
  // 标签云失败不阻塞挑题
  api.get('/problems/tags')
    .then((r: any) => { tagCloud.value = r.items ?? [] })
    .catch(() => { /* ignore */ })
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
.page-head h2 { margin: 0; }
.head-actions { display: flex; align-items: center; gap: 8px; }
.steps { max-width: 420px; margin-bottom: 14px; }
/* 左候选 + 右已选 */
.pick-grid {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.cand-panel {
  flex: 1;
  min-width: 0;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: 6px 14px 14px;
  background: var(--oj-surface);
}
.picked-panel {
  flex: 0 0 320px;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: 0 14px 14px;
  background: var(--oj-surface);
  position: sticky;
  top: 16px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid var(--oj-line-soft);
}
.panel-title { font-weight: 700; font-size: 14px; }
.filter-row {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.kw-input { max-width: 240px; }
.tag-sel { max-width: 280px; }
.fill-table { width: 100%; }
.row-tag { margin-right: 4px; }
.no-tag { color: var(--oj-ink-4); font-size: 13px; }
.pager {
  margin-top: 10px;
  justify-content: flex-end;
}
.pick-hint {
  color: var(--oj-ink-3);
  font-size: 13px;
  padding: 12px 0;
}
.foot-btns {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
/* ===== 视觉刷新：统一页面骨架（追加层，保证同特异性下胜出） ===== */
.page {
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
}
.page-head,
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.page-head h2,
.page-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s4);
}
.spacer { flex: 1; }
.mono-id,
.mono {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--oj-ink-3);
}
.muted,
.tip,
.pick-hint,
.form-tip,
.data-hint,
.err-msg {
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.section { margin-top: var(--oj-s6); }
.section h4 {
  margin: 0 0 var(--oj-s3);
  font-size: var(--oj-fs-lg);
}
.stat-card {
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.stat-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateY(-1px);
}
.stat-value {
  font-family: var(--oj-font-mono);
  font-size: 26px;
  letter-spacing: -0.02em;
  color: var(--oj-ink);
}
.stat-label {
  margin-top: 4px;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0;
}
.click-table,
.fill-table,
.cases-table,
.verify-table,
.log-list {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}

/* ===== 逻辑复查：标签筛选弹窗 ===== */
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { margin: 0; font-size: 24px; letter-spacing: -0.02em; }
.tag-filter-btn { position: relative; }
.tag-count {
  margin-left: 6px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--oj-accent);
  color: #fff;
  font-size: 12px;
  line-height: 18px;
}
.picked-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.tag-search { margin-bottom: 10px; }
.tag-cloud-box {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
  padding: 2px;
}
.tag-n { color: var(--oj-ink-4); font-size: 12px; }
</style>
