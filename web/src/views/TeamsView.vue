<!--
  TeamsView.vue - 团队页
  我的团队列表 + 创建团队 + 成员管理（邀请码/角色/移除）
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>我的团队</h2>
      <div class="head-ops">
        <el-button size="small" @click="showJoin = true">凭邀请码加入</el-button>
        <el-button type="primary" size="small" @click="showCreate = true">创建团队</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && teams.length === 0" description="还没有加入任何团队" />

    <div class="team-list">
      <div v-for="t in teams" :key="t.id" class="team-card">
        <div class="team-main" @click="openTeam(t)">
          <span class="team-name">{{ t.name }}</span>
          <el-tag size="small" :type="t.my_role === 'owner' ? 'warning' : t.my_role === 'admin' ? 'success' : 'info'">
            {{ roleLabel(t.my_role) }}
          </el-tag>
          <p class="team-desc">{{ t.description || '暂无简介' }}</p>
        </div>
      </div>
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
          <el-button size="small" @click="genInvite">生成邀请码</el-button>
          <span v-if="inviteCode" class="invite-code">邀请码：<b>{{ inviteCode }}</b>（10 分钟内有效）</span>
        </div>

        <h4>成员（{{ detail.members?.length ?? detail.member_count ?? 0 }}）</h4>
        <div v-for="m in detail.members ?? []" :key="m.user_id" class="member-row">
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
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()
const teams = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const creating = ref(false)
const createForm = ref({ name: '', description: '' })

// 凭邀请码加入
const showJoin = ref(false)
const joinCode = ref('')
const joining = ref(false)

const showDetail = ref(false)
const detail = ref<any>(null)
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
  try {
    teams.value = await api.get('/teams') as any
  } finally {
    loading.value = false
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
.head-ops { display: flex; gap: 8px; }
.team-list { display: flex; flex-direction: column; gap: 10px; }
.team-card {
  padding: 14px 18px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}
.team-card:hover { box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); }
.team-name { font-weight: 600; margin-right: 10px; }
.team-desc { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 6px; }
.d-desc { color: var(--el-text-color-secondary); font-size: 13px; }
.d-actions { margin: 10px 0 16px; display: flex; align-items: center; gap: 10px; }
.invite-code { font-size: 13px; color: var(--el-color-primary); }
.member-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.m-name { flex: 1; }
.m-ops { display: flex; gap: 2px; }
</style>
