<!--
  PlaylistsView.vue - 题单列表 + 详情
  公有/私有题单，显示我的完成进度；有管理权者可编辑/删除题单（删除不可恢复）
  路由 /playlists（列表）与 /playlists/:id（详情，可直达/刷新）
-->
<template>
  <div class="page">
    <template v-if="!current">
      <header class="page-head">
        <div class="head-titles">
          <span class="oj-kicker">Playlists</span>
          <h2>题单</h2>
        </div>
        <el-button type="primary" size="small" @click="showCreate = true">创建题单</el-button>
      </header>

      <el-empty v-if="!loading && playlists.length === 0" description="暂无可见题单" />

      <div class="pl-list">
        <div v-for="pl in pagedPlaylists" :key="pl.id" class="pl-card" @click="open(pl)">
          <div class="pl-title-row">
            <span class="pl-title">{{ pl.title }}</span>
            <el-tag size="small" effect="plain" :type="pl.is_public ? 'success' : 'info'">
              {{ pl.is_public ? '公开' : '私有' }}
            </el-tag>
          </div>
          <p class="pl-desc">{{ pl.description || '暂无简介' }}</p>
        </div>
      </div>

      <div class="pager-row">
        <el-pagination v-if="playlists.length > pageSize" class="pager"
                       layout="total, prev, pager, next"
                       :total="playlists.length" :page-size="pageSize"
                       v-model:current-page="page" />
      </div>
    </template>

    <!-- 题单详情 -->
    <template v-else>
      <header class="page-head">
        <div class="head-titles">
          <el-button size="small" text class="back" @click="backToList">← 返回题单</el-button>
          <div class="title-line">
            <h2 class="d-title">{{ current.title }}</h2>
            <el-tag size="small" effect="plain"
                    :type="current.is_public ? 'success' : 'info'">
              {{ current.is_public ? '公开' : '私有' }}
            </el-tag>
          </div>
        </div>
        <div class="head-right">
          <span class="progress-label">
            已完成 <b>{{ solvedCount }}</b> / {{ current.problems?.length ?? 0 }}
          </span>
          <el-button v-if="canManage" size="small" type="primary"
                     @click="openEdit">编辑题单</el-button>
          <el-button v-if="canManage" size="small" type="danger" plain
                     @click="removeCurrent">删除题单</el-button>
        </div>
      </header>
      <el-table :data="pagedCurrentProblems" stripe class="detail-table">
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-icon v-if="solvedIds.includes(row.problem_id)" color="var(--el-color-success)">
              <CircleCheckFilled />
            </el-icon>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="#" width="90">
          <template #default="{ row }">{{ row.display_id }}</template>
        </el-table-column>
        <el-table-column label="题目名称" min-width="240">
          <template #default="{ row }">
            <!-- 题单内题目可见性只看题单本身：能进题单即可见（含私有题） -->
            <router-link :to="`/playlists/${current.id}/problems/${row.problem_id}`" class="t-link">
              {{ row.title }}
            </router-link>
          </template>
        </el-table-column>
        <el-table-column label="难度" width="100">
          <template #default="{ row }">
            <el-tag :type="diffTag(row.difficulty)" size="small">{{ diffLabel(row.difficulty) }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="currentProblemsTotal > currentProblemsPageSize" class="pager-row">
        <el-pagination class="pager" layout="total, prev, pager, next"
                       :total="currentProblemsTotal" :page-size="currentProblemsPageSize"
                       v-model:current-page="currentProblemsPage" />
      </div>
    </template>

    <!-- 创建题单 -->
    <el-dialog v-model="showCreate" title="创建题单" width="460">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="createForm.title" maxlength="128" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="可见性">
          <el-switch v-model="createForm.is_public" active-text="公开" inactive-text="私有" />
        </el-form-item>
        <el-form-item label="归属">
          <el-select v-model="createForm.owner_type" style="width:140px">
            <el-option label="我的账号" value="user" />
            <el-option v-for="t in myTeams" :key="t.id" :label="`团队：${t.name}`" value="team" />
          </el-select>
          <el-select v-if="createForm.owner_type === 'team'" v-model="createForm.team_id"
                     placeholder="选择团队" style="width:160px; margin-left:8px">
            <el-option v-for="t in manageableTeams" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑题单：基本信息 + 题目增删排序 -->
    <el-dialog v-model="showEdit" title="编辑题单" width="640" :close-on-click-modal="false">
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" maxlength="128" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="可见性">
          <el-switch v-model="editForm.is_public" active-text="公开" inactive-text="私有" />
        </el-form-item>
        <el-form-item label="题目列表">
          <div class="edit-problems">
            <div v-for="(pid, i) in pagedEditProblems" :key="pid" class="ep-row">
              <span class="ep-idx">{{ editProblemOffset + i + 1 }}.</span>
              <span class="ep-title">{{ problemTitle(pid) }}</span>
              <el-button size="small" text :disabled="editProblemOffset + i === 0"
                         @click="moveUp(editProblemOffset + i)">↑</el-button>
              <el-button size="small" text
                         :disabled="editProblemOffset + i === editForm.problem_ids.length - 1"
                         @click="moveDown(editProblemOffset + i)">↓</el-button>
              <el-button size="small" text type="danger"
                         @click="removeProblem(editProblemOffset + i)">移除</el-button>
            </div>
            <div v-if="editProblemsTotal > editProblemsPageSize" class="pager-row">
              <el-pagination class="pager" layout="total, prev, pager, next"
                             :total="editProblemsTotal" :page-size="editProblemsPageSize"
                             v-model:current-page="editProblemsPage" />
            </div>
            <el-empty v-if="editForm.problem_ids.length === 0" description="暂无题目"
                      :image-size="50" />
            <div class="ep-add">
              <el-button size="small" @click="openChoose">＋ 添加题目</el-button>
              <span class="ep-hint">从题库搜索并选择，可连续添加多题</span>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 选择题目：题库量大，独立弹窗内搜索 + 点选（已选中的点一下即移除） -->
    <el-dialog v-model="showChoose" title="添加题目" width="560" append-to-body>
      <el-input v-model="chooseKw" placeholder="输入题名 / 题号搜索" clearable />
      <p class="choose-tip">已选 {{ editForm.problem_ids.length }} 题 · 点击题目加入或移除</p>
      <div class="filter-list">
        <div v-for="p in pagedChooseList" :key="p.id" class="filter-item"
             :class="{ 'is-active': editForm.problem_ids.includes(p.id) }"
             @click="toggleProblem(p.id)">
          <span class="fi-id">{{ p.display_id }}</span>
          <span class="fi-title">{{ p.title }}</span>
          <span class="fi-mark">{{ editForm.problem_ids.includes(p.id) ? '已选' : '＋' }}</span>
        </div>
        <el-empty v-if="chooseList.length === 0" description="无匹配题目" :image-size="60" />
        <div v-if="chooseTotal > choosePageSize" class="pager-row">
          <el-pagination class="pager" layout="total, prev, pager, next"
                         :total="chooseTotal" :page-size="choosePageSize"
                         v-model:current-page="choosePage" />
        </div>
      </div>
      <template #footer>
        <el-button type="primary" @click="showChoose = false">完成</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'
import { useClientPager } from '../composables/useClientPager'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const playlists = ref<any[]>([])
const myTeams = ref<any[]>([])
const allProblems = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ title: '', description: '', is_public: false, owner_type: 'user', team_id: null as number | null })
const current = ref<any>(null)

// 题单内题目可能上百：详情表预留分页
const { page: currentProblemsPage, size: currentProblemsPageSize,
  total: currentProblemsTotal, paged: pagedCurrentProblems } =
  useClientPager(computed<any[]>(() => current.value?.problems ?? []), 20)
// 列表分页：接口返回全部可见题单，页面内分页展示
const page = ref(1)
const pageSize = 8
const pagedPlaylists = computed(() =>
  playlists.value.slice((page.value - 1) * pageSize, page.value * pageSize))

// 编辑题单
const showEdit = ref(false)
const saving = ref(false)
const editForm = ref({ title: '', description: '', is_public: false, problem_ids: [] as number[] })

// 我能否管理当前题单（后端仍是权威校验，这里只是入口展示）
// 个人题单=本人；团队题单=队长/副队；ADMIN 总是
const canManage = computed(() => {
  if (!current.value) return false
  if (userStore.user?.role === 'admin') return true
  if (current.value.owner_type === 'user') {
    return current.value.owner_id === userStore.user?.id
  }
  if (current.value.owner_type === 'team') {
    const t = myTeams.value.find((x) => x.id === current.value.team_id)
    return t ? ['owner', 'admin'].includes(t.my_role) : false
  }
  return false
})

// 删除题单：硬删除不可恢复；playlist_problems 关联随之清除，题目本身不受影响
async function removeCurrent() {
  await ElMessageBox.confirm(
    `删除后题单「${current.value.title}」及其题目清单将被永久移除，不可恢复！题目本身不受影响。`,
    '删除题单', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
  try {
    await api.delete(`/playlists/${current.value.id}`)
    ElMessage.success('已删除')
    backToList()
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '删除失败')
  }
}

// 团队题单只允许队长/副队创建
const manageableTeams = computed(() =>
  myTeams.value.filter((t) => ['owner', 'admin'].includes(t.my_role)))

const solvedIds = computed(() => current.value?.solved_problem_ids ?? [])
const solvedCount = computed(() =>
  (current.value?.problems ?? []).filter((p: any) => solvedIds.value.includes(p.problem_id)).length)

const problemTitle = (pid: number) => {
  const p = (current.value?.problems ?? []).find((x: any) => x.problem_id === pid)
  return p ? `${p.display_id}. ${p.title}` : `#${pid}`
}

function openEdit() {
  editForm.value = {
    title: current.value.title,
    description: current.value.description,
    is_public: current.value.is_public,
    problem_ids: (current.value.problems ?? []).map((p: any) => p.problem_id),
  }
  showEdit.value = true
}

// 选择题目弹窗：把「从题库挑题」从编辑表单内联下拉拆成独立弹窗
const showChoose = ref(false)
const chooseKw = ref('')

// 题单可含上百题、题库更大：编辑列表与选题弹窗均预留分页
const { page: editProblemsPage, size: editProblemsPageSize, total: editProblemsTotal, paged: pagedEditProblems } =
  useClientPager(computed<any[]>(() => editForm.value.problem_ids), 10)
const editProblemOffset = computed(() => (editProblemsPage.value - 1) * editProblemsPageSize.value)
const { page: choosePage, size: choosePageSize, total: chooseTotal, paged: pagedChooseList } =
  useClientPager(computed<any[]>(() => chooseList.value), 20)
// 搜索词变化时回到第一页
watch(chooseKw, () => { choosePage.value = 1 })
const chooseList = computed(() => {
  const kw = chooseKw.value.trim().toLowerCase()
  const list = kw
    ? allProblems.value.filter((p) => `${p.display_id}. ${p.title}`.toLowerCase().includes(kw))
    : allProblems.value
  return list.slice(0, 300)
})

function openChoose() {
  chooseKw.value = ''
  showChoose.value = true
}

function toggleProblem(pid: number) {
  const arr = editForm.value.problem_ids
  const i = arr.indexOf(pid)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(pid)
}

function removeProblem(i: number) {
  editForm.value.problem_ids.splice(i, 1)
}

function moveUp(i: number) {
  const arr = editForm.value.problem_ids
  ;[arr[i - 1], arr[i]] = [arr[i], arr[i - 1]]
}

function moveDown(i: number) {
  const arr = editForm.value.problem_ids
  ;[arr[i], arr[i + 1]] = [arr[i + 1], arr[i]]
}

async function saveEdit() {
  if (!editForm.value.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  saving.value = true
  try {
    await api.put(`/playlists/${current.value.id}`, {
      title: editForm.value.title,
      description: editForm.value.description,
      is_public: editForm.value.is_public,
    })
    await api.put(`/playlists/${current.value.id}/problems`, {
      problem_ids: editForm.value.problem_ids,
    })
    ElMessage.success('保存成功')
    showEdit.value = false
    current.value = await api.get(`/playlists/${current.value.id}`) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

async function load() {
  loading.value = true
  page.value = 1
  try {
    playlists.value = await api.get('/playlists') as any
    try {
      myTeams.value = await api.get('/teams') as any
      // 出题视角选题：拉自己管理的题目（含私有草稿题，可加进题单）
      allProblems.value = await api.get('/problems?mine=1') as any
    } catch { /* 未登录忽略 */ }
  } finally {
    loading.value = false
  }
}

// 打开题单详情（路由跳转到 /playlists/:id，刷新/直达也能恢复）
async function open(pl: any) {
  await router.push(`/playlists/${pl.id}`)
}

// 返回列表（清掉路由里的 id）
function backToList() {
  router.push('/playlists')
}

// 从路由参数恢复详情（进入页面时带 id / 点卡片跳转 / 浏览器前进后退）
async function openFromRoute() {
  const pid = route.params.id as string | undefined
  if (!pid) {
    current.value = null
    return
  }
  try {
    current.value = await api.get(`/playlists/${pid}`) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '题单不存在或无权访问')
    router.replace('/playlists')
  }
}

// 只在路由 id 变化时拉详情；列表数据未加载时先补一次列表
watch(() => route.params.id, async (pid, old) => {
  if (route.name !== 'playlist-detail' && route.name !== 'playlists') return
  if (String(pid ?? '') === String(old ?? '')) return
  if (pid) {
    await openFromRoute()
  } else {
    current.value = null
  }
  if (playlists.value.length === 0 && !loading.value) load()
}, { immediate: true })

onMounted(() => {
  if (playlists.value.length === 0 && !loading.value && !route.params.id) load()
})

async function create() {
  if (!createForm.value.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  if (createForm.value.owner_type === 'team' && !createForm.value.team_id) {
    ElMessage.warning('请选择团队')
    return
  }
  creating.value = true
  try {
    await api.post('/playlists', createForm.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.page {
  height: 100%;
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s4);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.head-titles { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.head-titles h2 { font-size: 26px; letter-spacing: -0.02em; }
.back { align-self: flex-start; margin-bottom: 2px; color: var(--oj-ink-3); }
.back:hover { color: var(--oj-accent); }
.title-line { display: flex; align-items: center; gap: var(--oj-s2); }
.d-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
}

.pl-list { display: flex; flex-direction: column; gap: var(--oj-s3); }
.pl-card {
  position: relative;
  padding: var(--oj-s4) var(--oj-s6) var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  cursor: pointer;
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
/* 悬停时右侧浮出箭头，暗示可进入 */
.pl-card::after {
  content: '→';
  position: absolute;
  right: var(--oj-s5);
  top: 50%;
  transform: translateY(-50%);
  font-size: var(--oj-fs-lg);
  color: var(--oj-accent);
  opacity: 0;
  transition: opacity var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.pl-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateX(2px);
}
.pl-card:hover::after { opacity: 1; transform: translateY(-50%) translateX(2px); }
.pl-title-row { display: flex; align-items: center; gap: var(--oj-s2); }
.pl-title {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-lg);
  font-weight: 600;
  color: var(--oj-ink);
}
.pl-desc {
  margin-top: 6px;
  max-width: 72ch;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-md);
}

.head-right { display: flex; align-items: center; gap: var(--oj-s3); }
.progress-label { color: var(--oj-ink-3); font-size: var(--oj-fs-md); }
.progress-label b {
  font-family: var(--oj-font-mono);
  font-weight: 600;
  color: var(--oj-accent);
}
.detail-table {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}

/* 编辑题单弹窗内的题目列表 */
.edit-problems { width: 100%; }
.ep-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 0;
  border-bottom: 1px solid var(--oj-line-soft);
}
.ep-idx {
  width: 30px;
  font-family: var(--oj-font-mono);
  color: var(--oj-ink-4);
}
.ep-title { flex: 1; font-size: var(--oj-fs-md); }
.ep-add { margin-top: var(--oj-s3); display: flex; align-items: center; gap: var(--oj-s3); }
.ep-hint { color: var(--oj-ink-4); font-size: var(--oj-fs-xs); }

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s4) 0 0;
}

/* 选择题目弹窗 */
.choose-tip { margin: var(--oj-s3) 0 0; color: var(--oj-ink-3); font-size: var(--oj-fs-sm); }
.filter-list {
  margin-top: var(--oj-s2);
  max-height: 46vh;
  overflow-y: auto;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
}
.filter-item {
  display: flex;
  align-items: center;
  gap: var(--oj-s3);
  padding: 8px var(--oj-s4);
  cursor: pointer;
  border-bottom: 1px solid var(--oj-line-soft);
  transition: background var(--oj-dur-1) var(--oj-ease),
              color var(--oj-dur-1) var(--oj-ease);
}
.filter-item:last-child { border-bottom: none; }
.filter-item:hover { background: var(--oj-surface-2); }
.filter-item.is-active { background: var(--oj-accent-soft); }
.filter-item.is-active .fi-title { color: var(--oj-accent); }
.fi-id {
  min-width: 54px;
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-sm);
  color: var(--oj-ink-4);
}
.fi-title { flex: 1; font-size: var(--oj-fs-md); }
.fi-mark { color: var(--oj-ink-4); font-size: var(--oj-fs-sm); }
.filter-item.is-active .fi-mark { color: var(--oj-accent); }
.t-link {
  font-weight: 500;
  color: var(--oj-ink);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: color var(--oj-dur-1) var(--oj-ease),
              border-color var(--oj-dur-1) var(--oj-ease);
}
.t-link:hover { color: var(--oj-accent); border-bottom-color: var(--oj-accent); }
.muted { color: var(--oj-ink-4); }
</style>
