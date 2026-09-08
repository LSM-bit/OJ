<!--
  PlaylistsView.vue - 题单列表 + 详情
  公有/私有题单，显示我的完成进度
  路由 /playlists（列表）与 /playlists/:id（详情，可直达/刷新）
-->
<template>
  <div class="page">
    <template v-if="!current">
      <div class="page-head">
        <h2>题单</h2>
        <el-button type="primary" size="small" @click="showCreate = true">创建题单</el-button>
      </div>

      <el-empty v-if="!loading && playlists.length === 0" description="暂无可见题单" />

      <div class="pl-list">
        <div v-for="pl in playlists" :key="pl.id" class="pl-card" @click="open(pl)">
          <div class="pl-title-row">
            <span class="pl-title">{{ pl.title }}</span>
            <el-tag size="small" :type="pl.is_public ? 'success' : 'info'">
              {{ pl.is_public ? '公开' : '私有' }}
            </el-tag>
          </div>
          <p class="pl-desc">{{ pl.description || '暂无简介' }}</p>
        </div>
      </div>
    </template>

    <!-- 题单详情 -->
    <template v-else>
      <div class="page-head">
        <div>
          <el-button size="small" text @click="backToList">← 返回</el-button>
          <span class="d-title">{{ current.title }}</span>
          <el-tag size="small" :type="current.is_public ? 'success' : 'info'" style="margin-left:8px">
            {{ current.is_public ? '公开' : '私有' }}
          </el-tag>
        </div>
        <div class="head-right">
          <span class="progress-label">
            已完成 {{ solvedCount }} / {{ current.problems?.length ?? 0 }}
          </span>
          <el-button v-if="canManage" size="small" type="primary"
                     @click="openEdit">编辑题单</el-button>
        </div>
      </div>
      <el-table :data="current.problems ?? []" stripe>
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
            <div v-for="(pid, i) in editForm.problem_ids" :key="pid" class="ep-row">
              <span class="ep-idx">{{ i + 1 }}.</span>
              <span class="ep-title">{{ problemTitle(pid) }}</span>
              <el-button size="small" text :disabled="i === 0" @click="moveUp(i)">↑</el-button>
              <el-button size="small" text :disabled="i === editForm.problem_ids.length - 1"
                         @click="moveDown(i)">↓</el-button>
              <el-button size="small" text type="danger" @click="removeProblem(i)">移除</el-button>
            </div>
            <el-empty v-if="editForm.problem_ids.length === 0" description="暂无题目"
                      :image-size="50" />
            <div class="ep-add">
              <el-select v-model="addProblemId" filterable placeholder="搜索并添加题目"
                         style="flex:1" @change="addProblem">
                <el-option v-for="p in allProblems" :key="p.id"
                           :label="`${p.display_id}. ${p.title}`" :value="p.id" />
              </el-select>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

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

// 编辑题单
const showEdit = ref(false)
const saving = ref(false)
const editForm = ref({ title: '', description: '', is_public: false, problem_ids: [] as number[] })
const addProblemId = ref<number | null>(null)

// 我能否编辑当前题单（后端仍是权威校验，这里只是入口展示）
const canManage = computed(() => {
  if (!current.value) return false
  if (userStore.user?.role === 'admin') return true
  return current.value.owner_type === 'user' &&
    current.value.owner_id === userStore.user?.id
})

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

function addProblem() {
  if (addProblemId.value == null) return
  if (!editForm.value.problem_ids.includes(addProblemId.value)) {
    editForm.value.problem_ids.push(addProblemId.value)
  }
  addProblemId.value = null
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
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.pl-list { display: flex; flex-direction: column; gap: 10px; }
.pl-card {
  padding: 14px 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}
.pl-card:hover { box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); }
.pl-title-row { display: flex; align-items: center; gap: 10px; }
.pl-title { font-weight: 600; }
.pl-desc { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 6px; }
.d-title { font-size: 17px; font-weight: 700; margin-left: 8px; }
.head-right { display: flex; align-items: center; gap: 12px; }
.progress-label { color: var(--el-text-color-secondary); font-size: 13px; }

/* 编辑题单弹窗内的题目列表 */
.edit-problems { width: 100%; }
.ep-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.ep-idx { width: 30px; color: var(--el-text-color-secondary); }
.ep-title { flex: 1; font-size: 13px; }
.ep-add { margin-top: 8px; display: flex; }
.t-link { color: var(--el-color-primary); text-decoration: none; }
.t-link:hover { text-decoration: underline; }
.muted { color: var(--el-text-color-placeholder); }
</style>
