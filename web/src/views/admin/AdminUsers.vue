<!--
  AdminUsers.vue - 后台用户管理：列表/搜索/改角色/封禁解封
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-input v-model="q" placeholder="搜索用户名/邮箱" clearable style="width: 240px"
                @keyup.enter="load" @clear="load" />
      <el-button type="primary" @click="load">搜索</el-button>
    </div>

    <el-table :data="items" v-loading="loading" height="calc(100vh - 160px)">
      <el-table-column label="ID" width="180">
        <template #default="{ row }">
          <span class="mono-id" :title="row.id">{{ row.id }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="email" label="邮箱" min-width="180" />
      <el-table-column label="角色" width="160">
        <template #default="{ row }">
          <el-select :model-value="row.role" size="small"
                     @change="(v: string) => changeRole(row, v)">
            <el-option label="普通用户" value="user" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="rating" label="Rating" width="90" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag size="small" :type="row.banned ? 'danger' : 'success'">
            {{ row.banned ? '已封禁' : '正常' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="注册时间" width="170">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="110">
        <template #default="{ row }">
          <el-button v-if="!row.banned" size="small" type="danger" text @click="setBan(row, true)">
            封禁
          </el-button>
          <el-button v-else size="small" type="warning" text @click="setBan(row, false)">
            解封
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination class="pager" layout="total, prev, pager, next" :total="total"
                   :page-size="pageSize" :current-page="page"
                   @current-change="(p: number) => { page = p; load() }" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'

const items = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const q = ref('')
const loading = ref(false)

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 16) : '')

async function load() {
  loading.value = true
  try {
    const r = await api.get('/admin/users', { params: { q: q.value, page: page.value } }) as any
    items.value = r.items ?? []
    total.value = r.total ?? 0
  } finally {
    loading.value = false
  }
}

async function changeRole(row: any, role: string) {
  await ElMessageBox.confirm(`确认将 ${row.username} 的角色改为 ${role}？`, '修改角色')
  try {
    await api.put(`/admin/users/${row.id}/role`, { role })
    ElMessage.success('已修改')
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '修改失败')
    await load()
  }
}

async function setBan(row: any, banned: boolean) {
  await ElMessageBox.confirm(
    `确认${banned ? '封禁' : '解封'} ${row.username}？${banned ? '其现有登录将立即失效' : ''}`,
    banned ? '封禁用户' : '解封用户')
  try {
    await api.put(`/admin/users/${row.id}/ban`, { banned })
    ElMessage.success(banned ? '已封禁' : '已解封')
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
}
.toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.pager {
  margin-top: 10px;
  justify-content: flex-end;
}
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
</style>
