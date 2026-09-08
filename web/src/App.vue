<!--
  App.vue - 全局布局
  顶栏导航 + 内容区占满剩余视口（各页面自行滚动）
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from './stores/user'
import { api } from './api/client'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 菜单高亮：出题相关路由（/problems/new、/problems/:id/edit、/manage/*）都归到「出题」
const activeMenu = computed(() => {
  const p = route.path
  if (p.startsWith('/manage')) return '/manage'
  if (p.endsWith('/new') || p.endsWith('/edit')) return '/manage'
  return p
})

// 刷新页面后用 localStorage 里的 token 恢复用户信息
onMounted(() => {
  userStore.fetchMe()
  if (userStore.isLoggedIn) loadCheckin()
})

function logout() {
  userStore.logout()
  router.push('/')
}

// ---------------- 右上角用户下拉 ----------------
// 头像字符：用户名首字母（大写，无头像时兜底）
const avatarChar = computed(() =>
  (userStore.user?.username ?? '?').charAt(0).toUpperCase())
// 头像 URL：后端存相对路径 /static/avatars/xxx，需拼 API 域名
const avatarUrl = computed(() => {
  const a = userStore.user?.avatar
  return a ? `${api.defaults.baseURL}${a}` : ''
})

function onDropdownCommand(cmd: string) {
  if (cmd === 'profile') router.push('/profile')
  else if (cmd === 'logout') logout()
}

// ---------------- 每日打卡 ----------------
const showCheckin = ref(false)
const checkinInfo = ref<any>(null)
const checkingIn = ref(false)

async function loadCheckin() {
  try {
    checkinInfo.value = await api.get('/misc/checkin') as any
  } catch { /* 未登录/接口异常静默 */ }
}

async function openCheckin() {
  showCheckin.value = true
  await loadCheckin()
}

async function doCheckin() {
  checkingIn.value = true
  try {
    await api.post('/misc/checkin')
    ElMessage.success('打卡成功！')
    await loadCheckin()
  } catch (e: any) {
    ElMessage.info(e.response?.data?.detail ?? '打卡失败')
    await loadCheckin()
  } finally {
    checkingIn.value = false
  }
}
</script>

<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="logo" @click="router.push('/')">OJ</div>
      <el-menu mode="horizontal" router :default-active="activeMenu" :ellipsis="false">
        <el-menu-item index="/problems">题目</el-menu-item>
        <el-menu-item index="/contests">比赛</el-menu-item>
        <el-menu-item index="/playlists">题单</el-menu-item>
        <el-menu-item index="/teams">团队</el-menu-item>
        <el-menu-item v-if="userStore.isLoggedIn" index="/manage">出题</el-menu-item>
        <el-menu-item v-if="userStore.isLoggedIn" index="/submissions">提交记录</el-menu-item>
        <el-menu-item v-if="userStore.user?.role === 'admin'" index="/admin">后台</el-menu-item>
      </el-menu>
      <div class="spacer" />
      <template v-if="userStore.isLoggedIn">
        <!-- 打卡入口（右上） -->
        <el-badge :value="checkinInfo?.checked_today ? '' : '未打'" :hidden="!checkinInfo">
          <el-button size="small" :type="checkinInfo?.checked_today ? 'success' : 'warning'"
                     plain @click="openCheckin">
            📅 打卡
          </el-button>
        </el-badge>
        <!-- 用户头像：悬停展开个人中心/退出登录 -->
        <el-dropdown trigger="hover" @command="onDropdownCommand">
          <span class="avatar-wrap">
            <el-avatar :size="32" class="avatar" :src="avatarUrl || undefined">
              {{ avatarChar }}
            </el-avatar>
            <span class="username">{{ userStore.user?.username }}</span>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人中心</el-dropdown-item>
              <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
      <el-button v-else text @click="router.push('/login')">登录 / 注册</el-button>
    </el-header>

    <!-- 打卡弹窗 -->
    <el-dialog v-model="showCheckin" title="每日打卡" width="360" align-center>
      <div class="checkin-body">
        <div class="checkin-streak">
          <span class="streak-num">{{ checkinInfo?.streak ?? 0 }}</span>
          <span class="streak-label">连续天数</span>
        </div>
        <div class="checkin-meta">
          累计打卡 {{ checkinInfo?.total ?? 0 }} 天
          <template v-if="checkinInfo?.checked_today">｜ 今日已打卡 ✓</template>
        </div>
        <el-button v-if="!checkinInfo?.checked_today" type="primary" size="large"
                   :loading="checkingIn" @click="doCheckin" style="margin-top:16px">
          立即打卡
        </el-button>
        <el-tag v-else type="success" size="large" effect="light" style="margin-top:16px">
          今天已打卡，明天再来！
        </el-tag>
      </div>
    </el-dialog>
    <el-main class="main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100vh;
  display: flex;
  flex-direction: column;
}
.header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
  background: #fff;
  padding: 0 20px;
}
.logo {
  font-size: 22px;
  font-weight: 700;
  cursor: pointer;
  color: var(--el-color-primary);
}
.spacer {
  flex: 1;
}
.username { font-size: 14px; }

/* 右上角头像 + 用户名（下拉触发器） */
.avatar-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
  padding: 4px 6px;
  border-radius: 6px;
}
.avatar-wrap:hover { background: var(--el-fill-color-light); }
.avatar {
  background: var(--el-color-primary);
  color: #fff;
  font-weight: 600;
}

/* 打卡弹窗 */
.checkin-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
}
.checkin-streak { text-align: center; }
.streak-num {
  font-size: 44px;
  font-weight: 700;
  color: var(--el-color-primary);
}
.streak-label {
  display: block;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.checkin-meta {
  margin-top: 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

/* 内容区占满剩余高度，滚动交给页面内部 */
.main {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
}
</style>
