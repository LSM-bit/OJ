<!--
  App.vue - 全局布局
  顶栏导航 + 内容区占满剩余视口（各页面自行滚动）
-->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from './stores/user'
import AiAssistant from './components/AiAssistant.vue'
import { api } from './api/client'
import { useClientPager } from './composables/useClientPager'
import md from './utils/markdown'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

// 导航高亮：把子路由归并回它的一级入口（详情页仍高亮所属版块）
const NAV_ROOTS = ['/problems', '/contests', '/playlists', '/teams', '/submissions', '/admin']
const activeMenu = computed(() => {
  const p = route.path
  // 出题相关（/manage/*、/problems/new、/problems/:id/edit）都归到「创作」
  if (p.startsWith('/manage') || p === '/problems/new' || /^\/problems\/[^/]+\/edit$/.test(p)) {
    return '/manage'
  }
  return NAV_ROOTS.find((root) => p === root || p.startsWith(`${root}/`)) ?? p
})

// 顶部导航项（命名与可见性随登录态变化）
const navItems = computed(() => {
  const items: { path: string; label: string }[] = [
    { path: '/problems', label: '题库' },
    { path: '/contests', label: '竞赛' },
    { path: '/playlists', label: '题单' },
    { path: '/teams', label: '团队' },
  ]
  if (userStore.isLoggedIn) {
    items.push({ path: '/manage', label: '创作' }, { path: '/submissions', label: '提交' })
  }
  if (userStore.user?.role === 'admin') items.push({ path: '/admin', label: '管理' })
  return items
})

// 刷新页面后用 localStorage 里的 token 恢复用户信息
onMounted(() => {
  userStore.fetchMe()
  loadAnnouncements()
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

// ---------------- 公告（占据原打卡入口位，列表 + 详情） ----------------
const announcements = ref<any[]>([])
// 公告随运营持续增加：预留分页
const { page: annPage, size: annPageSize, total: annTotal, paged: pagedAnnouncements } =
  useClientPager(computed<any[]>(() => announcements.value), 5)
const showAnn = ref(false)
const currentAnn = ref<any>(null)
const renderedAnn = computed(() =>
  currentAnn.value ? md.render(currentAnn.value.content ?? '') : '')

async function loadAnnouncements() {
  try {
    announcements.value = await api.get('/misc/announcements') as any
  } catch { /* 接口异常静默：无公告不阻塞页面 */ }
}

function openAnnouncements() {
  currentAnn.value = null
  annPage.value = 1
  showAnn.value = true
  if (!announcements.value.length) loadAnnouncements()
}

function viewAnnounce(a: any) {
  currentAnn.value = a
}

function backToList() {
  currentAnn.value = null
}
</script>

<template>
  <div class="shell">
    <!-- 顶栏：品牌 + 主导航 + 会话区 -->
    <header class="topbar">
      <div class="brand" role="link" tabindex="0"
           @click="router.push('/')" @keyup.enter="router.push('/')">
        <span class="brand-mark">衡</span>
        <span class="brand-text">
          <span class="brand-name">Online Judge</span>
          <span class="brand-sub">HENG · 评测系统</span>
        </span>
      </div>

      <nav class="nav">
        <button v-for="item in navItems" :key="item.path" type="button" class="nav-item"
                :class="{ active: activeMenu === item.path }" @click="router.push(item.path)">
          {{ item.label }}
        </button>
      </nav>

      <div class="spacer" />

      <div class="session">
        <!-- 公告：占据原打卡位（公开可见，有公告时才出现） -->
        <button v-if="announcements.length" type="button" class="announce"
                @click="openAnnouncements">
          <span class="announce-mark" />
          <span class="announce-label">公告</span>
          <span class="announce-count oj-num">{{ announcements.length }}</span>
        </button>

        <template v-if="userStore.isLoggedIn">
          <el-dropdown trigger="click" @command="onDropdownCommand">
            <span class="user">
              <span class="user-avatar" :class="{ 'has-img': !!avatarUrl }"
                    :style="avatarUrl ? { backgroundImage: `url(${avatarUrl})` } : undefined">
                <template v-if="!avatarUrl">{{ avatarChar }}</template>
              </span>
              <span class="user-name">{{ userStore.user?.username }}</span>
              <span class="user-caret">▾</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <router-link v-else class="signin" to="/login">登录 / 注册</router-link>
      </div>
    </header>

    <main class="main">
      <router-view v-slot="{ Component }">
        <transition name="route-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- 公告弹窗：列表 ⇄ 详情 -->
    <el-dialog v-model="showAnn" :title="currentAnn ? currentAnn.title : '公告'"
               width="520" align-center>
      <template v-if="!currentAnn">
        <div v-if="announcements.length" class="ann-list">
          <div v-for="a in pagedAnnouncements" :key="a.id" class="ann-item"
               @click="viewAnnounce(a)">
            <div class="ann-item-title">
              <el-tag v-if="a.top" type="danger" size="small" effect="dark">置顶</el-tag>
              {{ a.title }}
            </div>
            <div class="ann-item-date">{{ (a.created_at || '').slice(0, 10) }}</div>
          </div>
        </div>
        <el-empty v-else description="暂无公告" :image-size="60" />
        <div v-if="annTotal > annPageSize" class="pager-row">
          <el-pagination class="pager" layout="total, prev, pager, next"
                         :total="annTotal" :page-size="annPageSize"
                         v-model:current-page="annPage" />
        </div>
      </template>
      <template v-else>
        <div class="ann-meta">
          <el-tag v-if="currentAnn?.top" type="danger" size="small" effect="dark">置顶</el-tag>
          <span>{{ (currentAnn?.created_at || '').slice(0, 16).replace('T', ' ') }}</span>
        </div>
        <div class="ann-content markdown" v-html="renderedAnn"></div>
      </template>
      <template #footer>
        <el-button v-if="currentAnn" @click="backToList">返回列表</el-button>
        <el-button @click="showAnn = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>

  <!-- AI 助教悬浮球 + 抽屉（全局，登录后可见；组件内自判登录态） -->
  <AiAssistant />
</template>

<style scoped>
.shell {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--oj-paper);
}

/* ---------------------------------------------------------------- 顶栏 */
.topbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--oj-s5);
  height: 58px;
  padding: 0 var(--oj-s5);
  background: var(--oj-surface);
  border-top: 2px solid var(--oj-accent);   /* 顶部一条朱砂压线，全站唯一的品牌色块 */
  border-bottom: 1px solid var(--oj-line);
}
.spacer { flex: 1; }

/* 品牌：墨色方块 + 双行字标 */
.brand {
  display: flex;
  align-items: center;
  gap: 9px;
  cursor: pointer;
  user-select: none;
  outline: none;
}
.brand-mark {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  background: var(--oj-ink);
  color: var(--oj-surface);
  font-size: 15px;
  font-weight: 700;
  border-radius: var(--oj-r1);
  transition: background-color var(--oj-dur-2) var(--oj-ease);
}
.brand:hover .brand-mark { background: var(--oj-accent); }
.brand-text { display: flex; flex-direction: column; line-height: 1.2; }
.brand-name {
  font-family: var(--oj-font-display);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--oj-ink);
}
.brand-sub {
  font-size: 9px;
  letter-spacing: 0.16em;
  color: var(--oj-ink-4);
}

/* 主导航：贴底细线指示器，滑动而非闪现 */
.nav { display: flex; align-items: center; height: 100%; gap: 2px; }
.nav-item {
  position: relative;
  height: 100%;
  padding: 0 14px;
  border: 0;
  background: none;
  font-family: inherit;
  font-size: var(--oj-fs-md);
  color: var(--oj-ink-2);
  cursor: pointer;
  transition: color var(--oj-dur-2) var(--oj-ease),
              background-color var(--oj-dur-2) var(--oj-ease);
}
.nav-item::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: -1px;
  height: 2px;
  background: var(--oj-accent);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform var(--oj-dur-3) var(--oj-ease);
}
.nav-item:hover { color: var(--oj-ink); background: color-mix(in oklab, var(--oj-accent) 5%, transparent); }
.nav-item.active { color: var(--oj-ink); font-weight: 600; }
.nav-item.active::after { transform: scaleX(1); }

/* ------------------------------------------------------------ 会话区 */
.session { display: flex; align-items: center; gap: var(--oj-s3); }

/* 公告入口：占据原打卡位的胶囊按钮 */
.announce {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r-pill);
  background: var(--oj-surface);
  font-family: inherit;
  font-size: var(--oj-fs-md);
  color: var(--oj-ink-2);
  cursor: pointer;
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              background-color var(--oj-dur-2) var(--oj-ease),
              color var(--oj-dur-2) var(--oj-ease);
}
.announce:hover { border-color: var(--oj-ink-3); background: var(--oj-surface-2); color: var(--oj-ink); }
.announce:active { transform: translateY(1px); }
.announce-mark {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--oj-accent);
  flex-shrink: 0;
}
.announce-label { font-weight: 500; }
.announce-count { font-size: var(--oj-fs-xs); color: var(--oj-ink-3); }

/* 用户：方角头像 + 名字，点击展开菜单 */
.user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 8px 0 4px;
  border-radius: var(--oj-r2);
  cursor: pointer;
  outline: none;
  transition: background-color var(--oj-dur-2) var(--oj-ease);
}
.user:hover { background: var(--oj-surface-2); }
.user-avatar {
  width: 26px;
  height: 26px;
  border-radius: var(--oj-r1);
  display: grid;
  place-items: center;
  background: var(--oj-ink);
  background-size: cover;
  background-position: center;
  color: var(--oj-surface);
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
}
.user-avatar.has-img { color: transparent; }
.user-name { font-size: var(--oj-fs-md); color: var(--oj-ink); }
.user-caret { font-size: 9px; color: var(--oj-ink-4); }

.signin {
  display: inline-flex;
  align-items: center;
  height: 30px;
  padding: 0 14px;
  border: 1px solid color-mix(in oklab, var(--oj-accent) 45%, transparent);
  border-radius: var(--oj-r2);
  color: var(--oj-accent-deep);
  font-size: var(--oj-fs-md);
  text-decoration: none;
  transition: background-color var(--oj-dur-2) var(--oj-ease),
              border-color var(--oj-dur-2) var(--oj-ease),
              color var(--oj-dur-2) var(--oj-ease);
}
.signin:hover {
  background: var(--oj-accent);
  border-color: var(--oj-accent);
  color: #fff;
}

/* 内容区占满剩余高度，滚动交给页面内部 */
.main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* -------------------------------------------------------- 公告弹窗 */
.ann-list {
  max-height: 52vh;
  overflow-y: auto;
  margin: 0 calc(-1 * var(--oj-s2));
}
.ann-item {
  padding: 10px var(--oj-s2);
  border-bottom: 1px solid var(--oj-line-soft);
  cursor: pointer;
  transition: background-color var(--oj-dur-1) var(--oj-ease);
}
.ann-item:last-child { border-bottom: none; }
.ann-item:hover { background: var(--oj-surface-2); }
.ann-item-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--oj-fs-md);
  font-weight: 500;
  color: var(--oj-ink);
  word-break: break-all;
}
.ann-item-date {
  margin-top: 3px;
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  color: var(--oj-ink-4);
  letter-spacing: 0.02em;
}
.ann-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--oj-fs-xs);
  color: var(--oj-ink-3);
  margin-bottom: 10px;
}
.ann-content { max-height: 50vh; overflow-y: auto; }
</style>
