<!--
  TeamsView.vue - 团队页
  我的团队列表（含已归档筛选）+ 创建团队 + 成员管理（邀请码/角色/移除）+ 归档/解散
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Teams</span>
        <h2>我的团队</h2>
      </div>
      <div class="head-ops">
        <el-radio-group v-model="archived" size="small" @change="load">
          <el-radio-button :value="false">进行中</el-radio-button>
          <el-radio-button :value="true">已归档</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="showJoin = true">凭邀请码加入</el-button>
        <el-button type="primary" size="small" @click="showCreate = true">创建团队</el-button>
      </div>
    </header>

    <el-empty v-if="!loading && teams.length === 0"
              :description="archived ? '没有已归档的团队' : '还没有加入任何团队'" />

    <div class="team-list">
      <div v-for="t in pagedTeams" :key="t.id" class="team-card" @click="openTeam(t)">
        <div class="team-main">
          <div class="team-title-row">
            <span class="team-name">{{ t.name }}</span>
            <el-tag size="small" effect="plain"
                    :type="t.my_role === 'owner' ? 'warning' : t.my_role === 'admin' ? 'success' : 'info'">
              {{ roleLabel(t.my_role) }}
            </el-tag>
            <el-tag v-if="t.archived" size="small" type="info" effect="plain">已归档</el-tag>
          </div>
          <p class="team-desc">{{ t.description || '暂无简介' }}</p>
        </div>
        <span class="team-go">→</span>
      </div>
    </div>

    <div class="pager-row">
      <el-pagination v-if="teams.length > pageSize" class="pager"
                     layout="total, prev, pager, next" :total="teams.length"
                     :page-size="pageSize" v-model:current-page="page" />
    </div>

    <!-- 凭邀请码加入 -->
    <el-dialog v-model="showJoin" title="凭邀请码加入团队" width="400">
      <el-input v-model="joinCode" placeholder="输入队长/副队生成的邀请码" maxlength="20"
                @keyup.enter="join" />
      <template #footer>
        <el-button @click="showJoin = false">取消</el-button>
        <el-button type="primary" :loading="joining" @click="join">加入</el-button>
      </template>
    </el-dialog>

    <!-- 创建团队 -->
    <el-dialog v-model="showCreate" title="创建团队" width="420">
      <el-form label-width="70px">
        <el-form-item label="名称">
          <el-input v-model="createForm.name" maxlength="64" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="createForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="create">创建</el-button>
      </template>
    </el-dialog>

    <!-- 团队详情/管理 -->
    <el-drawer v-model="showDetail" :title="detail?.name ?? '团队'" size="420">
      <template v-if="detail">
        <p class="d-desc">{{ detail.description || '暂无简介' }}</p>
        <div class="d-actions" v-if="canManage">
          <el-button size="small" :disabled="detail.archived" @click="genInvite">生成邀请码</el-button>
          <span v-if="inviteCode" class="invite-code">邀请码：<b>{{ inviteCode }}</b>（10 分钟内有效）</span>
        </div>

        <!-- 归档/解散（仅队长/ADMIN 展示入口；后端为权威校验） -->
        <div class="d-actions" v-if="myRole === 'owner' || userStore.user?.role === 'admin'">
          <el-button v-if="!detail.archived" size="small" type="warning" plain
                     @click="setArchive(true)">归档团队</el-button>
          <el-button v-else size="small" type="success" plain
                     @click="setArchive(false)">恢复团队</el-button>
          <el-button v-if="!detail.archived" size="small" type="danger" plain
                     @click="disband">解散团队</el-button>
        </div>

        <h4>成员（{{ detail.members?.length ?? detail.member_count ?? 0 }}）</h4>
        <div v-for="m in pagedMembers" :key="m.user_id" class="member-row">
          <span class="m-name">{{ m.username }}</span>
          <el-tag size="small" :type="roleTag(m.role)">{{ roleLabel(m.role) }}</el-tag>
          <div class="m-ops" v-if="canManage && m.role !== 'owner'">
            <el-button v-if="m.role === 'member'" size="small" text type="primary"
                       @click="setRole(m, 'admin')">设为副队</el-button>
            <el-button v-else size="small" text type="primary"
                       @click="setRole(m, 'member')">取消副队</el-button>
            <el-button v-if="myRole === 'owner'" size="small" text type="warning"
                       @click="transferOwner(m)">转让队长</el-button>
            <el-button size="small" text type="danger" @click="removeMember(m)">移除</el-button>
          </div>
          <div class="m-ops" v-if="detail.my_role === 'member' && m.user_id === me?.id">
            <el-button size="small" text type="danger" @click="leave()">退出团队</el-button>
          </div>
        </div>
        <div v-if="membersTotal > membersPageSize" class="pager-row">
          <el-pagination class="pager" layout="total, prev, pager, next"
                         :total="membersTotal" :page-size="membersPageSize"
                         v-model:current-page="membersPage" />
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'
import { useClientPager } from '../composables/useClientPager'

const userStore = useUserStore()
const teams = ref<any[]>([])
const loading = ref(false)
// 客户端分页：接口返回我加入的全部团队，页面内分页展示
const page = ref(1)
const pageSize = 8
const pagedTeams = computed(() =>
  teams.value.slice((page.value - 1) * pageSize, page.value * pageSize))
watch(teams, () => {
  if ((page.value - 1) * pageSize >= teams.value.length) page.value = 1
})
const archived = ref(false) // 列表视角：false=进行中，true=已归档
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

// 凭邀请码加入
const showJoin = ref(false)
const joinCode = ref('')
const joining = ref(false)

const showDetail = ref(false)
const detail = ref<any>(null)

// 团队成员可能很多：前端预留分页
const { page: membersPage, size: membersPageSize, total: membersTotal, paged: pagedMembers } =
  useClientPager(computed<any[]>(() => detail.value?.members ?? []), 20)
const inviteCode = ref('')

const me = computed(() => userStore.user)
const myRole = computed(() => detail.value?.my_role)
const canManage = computed(() =>
  ['owner', 'admin'].includes(myRole.value) || userStore.user?.role === 'admin')

const roleLabel = (r: string) => ({ owner: '队长', admin: '副队长', member: '队员' }[r] ?? r)
const roleTag = (r: string) =>
  ({ owner: 'warning', admin: 'success', member: 'info' }[r] ?? 'info') as any

async function load() {
  loading.value = true
  page.value = 1
  try {
    teams.value = await api.get('/teams', {
      params: { archived: archived.value ? 1 : 0 },
    }) as any
  } catch (e: any) {
    // 未登录 / 无权限：退化为空列表，不把异常抛给 mounted
    teams.value = []
    if (userStore.isLoggedIn) {
      ElMessage.error(e.response?.data?.detail ?? '团队列表加载失败')
    }
  } finally {
    loading.value = false
  }
}

// 归档/恢复：仅队长可操作（后端权威校验）。归档后列表隐藏、成员不可加入，可随时恢复
async function setArchive(value: boolean) {
  if (value) {
    await ElMessageBox.confirm(
      '归档后团队将从列表隐藏，成员不能加入，名下题目/题单/比赛照常保留，可随时恢复。',
      '归档团队', { confirmButtonText: '归档', cancelButtonText: '取消' })
  }
  try {
    await api.put(`/teams/${detail.value.id}/archive`, { archived: value })
    ElMessage.success(value ? '已归档' : '已恢复')
    detail.value = await api.get(`/teams/${detail.value.id}`) as any
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

// 解散团队：硬删除，不可恢复
async function disband() {
  await ElMessageBox.confirm(
    '解散后团队及其成员关系将被永久删除，不可恢复！',
    '解散团队', { confirmButtonText: '解散', cancelButtonText: '取消', type: 'warning' })
  try {
    await api.delete(`/teams/${detail.value.id}`)
    ElMessage.success('已解散')
    showDetail.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '解散失败')
  }
}

async function create() {
  if (!createForm.value.name.trim()) {
    ElMessage.warning('请填写团队名')
    return
  }
  creating.value = true
  try {
    await api.post('/teams', createForm.value)
    ElMessage.success('创建成功')
    showCreate.value = false
    createForm.value = { name: '', description: '' }
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  } finally {
    creating.value = false
  }
}

async function openTeam(t: any) {
  detail.value = await api.get(`/teams/${t.id}`) as any
  inviteCode.value = ''
  showDetail.value = true
}

async function genInvite() {
  try {
    const r = await api.post(`/teams/${detail.value.id}/invite-codes`) as any
    inviteCode.value = r.code
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '生成失败')
  }
}

async function join() {
  if (!joinCode.value.trim()) {
    ElMessage.warning('请输入邀请码')
    return
  }
  joining.value = true
  try {
    await api.post('/teams/join', { code: joinCode.value.trim() })
    ElMessage.success('加入成功')
    showJoin.value = false
    joinCode.value = ''
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '加入失败')
  } finally {
    joining.value = false
  }
}

async function setRole(m: any, role: string) {
  try {
    await api.put(`/teams/${detail.value.id}/members/${m.user_id}/role`, { role })
    detail.value = await api.get(`/teams/${detail.value.id}`) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

async function transferOwner(m: any) {
  await ElMessageBox.confirm(`确认将队长转让给 ${m.username}？你将变为副队长`, '转让队长')
  try {
    await api.put(`/teams/${detail.value.id}/members/${m.user_id}/role`, { role: 'owner' })
    detail.value = await api.get(`/teams/${detail.value.id}`) as any
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '转让失败')
  }
}

async function removeMember(m: any) {
  try {
    await api.delete(`/teams/${detail.value.id}/members/${m.user_id}`)
    detail.value = await api.get(`/teams/${detail.value.id}`) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '移除失败')
  }
}

async function leave() {
  await ElMessageBox.confirm('确认退出该团队？', '退出团队')
  try {
    await api.delete(`/teams/${detail.value.id}/members/${me.value?.id}`)
    showDetail.value = false
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '退出失败')
  }
}

onMounted(load)
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
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { font-size: 26px; letter-spacing: -0.02em; }
.head-ops { display: flex; align-items: center; gap: var(--oj-s2); }

.team-list { display: flex; flex-direction: column; gap: var(--oj-s3); }
.team-card {
  display: flex;
  align-items: center;
  gap: var(--oj-s4);
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  cursor: pointer;
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.team-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateX(2px);
}
.team-main { flex: 1; min-width: 0; }
.team-title-row { display: flex; align-items: center; gap: var(--oj-s2); }
.team-name {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-lg);
  font-weight: 600;
  color: var(--oj-ink);
}
.team-desc {
  margin-top: 6px;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-md);
}
.team-go {
  flex-shrink: 0;
  color: var(--oj-ink-4);
  transition: color var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.team-card:hover .team-go { color: var(--oj-accent); transform: translateX(3px); }

/* 团队详情抽屉 */
.d-desc { color: var(--oj-ink-3); font-size: var(--oj-fs-md); }
.d-actions {
  margin: var(--oj-s3) 0 var(--oj-s4);
  display: flex;
  align-items: center;
  gap: var(--oj-s3);
}
.invite-code {
  font-size: var(--oj-fs-sm);
  color: var(--oj-ink-3);
}
.invite-code b {
  font-family: var(--oj-font-mono);
  color: var(--oj-accent);
  letter-spacing: 0.04em;
}
.member-row {
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  padding: var(--oj-s2) 0;
  border-bottom: 1px solid var(--oj-line-soft);
}
.member-row:last-child { border-bottom: none; }
.m-name { flex: 1; font-size: var(--oj-fs-md); }
.m-ops { display: flex; gap: 2px; }

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s4) 0;
}
</style>
