<template>
  <div class="page">
    <!-- Hero：品牌叙事 + 每日打卡（打卡自顶栏移入主页） -->
    <section class="hero">
      <div class="hero-copy">
        <span class="oj-kicker">Online Judge · HENG</span>
        <h1 class="hero-title">{{ heroTitle }}</h1>
        <p class="hero-sub">{{ heroSub }}</p>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="router.push('/problems')">
            进入题库
          </el-button>
          <el-button v-if="userStore.isLoggedIn" size="large"
                     @click="router.push('/submissions')">我的提交</el-button>
          <el-button v-else size="large" @click="router.push('/login')">登录 / 注册</el-button>
        </div>
      </div>

      <!-- 每日打卡 -->
      <aside class="checkin-panel">
        <div class="ck-head">
          <span class="oj-kicker">Daily Check-in</span>
          <span v-if="userStore.isLoggedIn" class="ck-state" :class="{ on: checkinInfo?.checked_today }">
            {{ checkinInfo?.checked_today ? '已打卡' : '待打卡' }}
          </span>
        </div>

        <template v-if="userStore.isLoggedIn">
          <div class="ck-streak">
            <span class="ck-num">{{ checkinInfo?.streak ?? '—' }}</span>
            <span class="ck-unit">天连续</span>
          </div>
          <div class="ck-meta">
            累计 <b class="oj-num">{{ checkinInfo?.total ?? '—' }}</b> 天
          </div>
          <button v-if="!checkinInfo?.checked_today" type="button" class="ck-btn"
                  :disabled="checkingIn" @click="doCheckin">
            {{ checkingIn ? '记录中…' : '立即打卡' }}
          </button>
          <div v-else class="ck-done">明天再来，保持连击</div>
        </template>

        <template v-else>
          <p class="ck-hint oj-muted">登录后每天来点一下，记录连续打卡天数。</p>
          <button type="button" class="ck-btn" @click="router.push('/login')">登录 / 注册</button>
        </template>
      </aside>
    </section>

    <!-- 快捷入口 -->
    <section class="sec">
      <header class="sec-head">
        <span class="oj-kicker">Navigate</span>
        <h3>快捷入口</h3>
      </header>
      <div class="entry-grid">
        <button v-for="e in entries" :key="e.path" type="button" class="entry"
                @click="router.push(e.path)">
          <span class="entry-name">{{ e.label }}</span>
          <span class="entry-desc">{{ e.desc }}</span>
        </button>
      </div>
    </section>

    <!-- 最新题目 -->
    <section class="sec">
      <header class="sec-head">
        <span class="oj-kicker">Latest</span>
        <h3>最新题目</h3>
        <span class="spacer" />
        <el-button link type="primary" size="small" @click="router.push('/problems')">
          查看全部
        </el-button>
      </header>
      <div v-if="latest.length" class="latest-list">
        <div v-for="p in latest" :key="p.id" class="latest-row"
             @click="router.push(`/problems/${p.id}`)">
          <span class="latest-id oj-num">#{{ p.display_id }}</span>
          <span class="latest-title">{{ p.title }}</span>
          <el-tag :type="diffTag(p.difficulty)" size="small">{{ diffLabel(p.difficulty) }}</el-tag>
        </div>
      </div>
      <el-empty v-else :description="loadingLatest ? '加载中…' : '暂无公开题目'" :image-size="60" />
    </section>
  </div>
</template>

<script setup lang="ts">
// 主页：品牌概览 + 每日打卡（自顶栏移入）+ 快捷入口 + 最新题目
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

// ---------------- 每日打卡 ----------------
const checkinInfo = ref<any>(null)
const checkingIn = ref(false)

async function loadCheckin() {
  if (!userStore.isLoggedIn) {
    checkinInfo.value = null
    return
  }
  try {
    checkinInfo.value = await api.get('/misc/checkin') as any
  } catch { /* 未登录 / 接口异常静默，不阻塞主页 */ }
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

// ---------------- 头部文案 ----------------
const heroTitle = computed(() => (userStore.isLoggedIn
  ? `欢迎回来，${userStore.user?.username ?? ''}`
  : '衡 · 在线评测'))
const heroSub = computed(() => (userStore.isLoggedIn
  ? '今天也想清楚一道题。题库、竞赛、提交与打卡都在这里。'
  : '做题、比赛、评测一站式。登录后记录你的每一次提交与打卡。'))

// ---------------- 快捷入口 ----------------
const entries = computed(() => {
  const list: { path: string; label: string; desc: string }[] = [
    { path: '/problems', label: '题库', desc: '公开题目，标签筛选' },
    { path: '/contests', label: '竞赛', desc: '报名、榜单与赛题' },
    { path: '/playlists', label: '题单', desc: '按主题成组刷题' },
    { path: '/teams', label: '团队', desc: '组队与队伍空间' },
  ]
  if (userStore.isLoggedIn) {
    list.push(
      { path: '/submissions', label: '提交', desc: '评测记录与详情' },
      { path: '/manage', label: '创作', desc: '出题与维护题目' },
    )
  }
  if (userStore.user?.role === 'admin') {
    list.push({ path: '/admin', label: '管理', desc: '用户 / 题目 / 日志' })
  }
  return list
})

// ---------------- 最新题目 ----------------
const latest = ref<any[]>([])
const loadingLatest = ref(false)

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) =>
  (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  loadCheckin()
  loadingLatest.value = true
  try {
    const r = await api.get('/problems', { params: { full: 1, page: 1, size: 6 } }) as any
    latest.value = r.items ?? []
  } catch { /* 静默 */ } finally {
    loadingLatest.value = false
  }
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
  overflow-y: auto;
}

/* ------------------------------------------------------------------ Hero */
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--oj-s6);
  padding: var(--oj-s5) 0 var(--oj-s6);
  border-bottom: 1px solid var(--oj-line);
}
.hero-copy {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--oj-s3);
  min-width: 0;
}
.hero-title {
  font-size: clamp(28px, 3vw + 12px, 44px);
  line-height: 1.1;
  letter-spacing: -0.03em;
}
.hero-sub {
  max-width: 54ch;
  font-size: var(--oj-fs-lg);
  color: var(--oj-ink-2);
}
.hero-actions { display: flex; gap: var(--oj-s2); margin-top: var(--oj-s2); }

/* ------------------------------------------------------------- 每日打卡 */
.checkin-panel {
  display: flex;
  flex-direction: column;
  gap: var(--oj-s3);
  min-height: 200px;
  padding: var(--oj-s4);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
}
.ck-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--oj-s2);
}
.ck-state {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--oj-ink-4);
}
.ck-state.on { color: var(--oj-ac); }
.ck-streak { display: flex; align-items: baseline; gap: var(--oj-s2); }
.ck-num {
  font-family: var(--oj-font-display);
  font-variant-numeric: tabular-nums;
  font-size: 50px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.03em;
  color: var(--oj-ink);
}
.ck-unit { font-size: var(--oj-fs-md); color: var(--oj-ink-3); }
.ck-meta { font-size: var(--oj-fs-md); color: var(--oj-ink-2); }
.ck-meta b { font-weight: 600; color: var(--oj-ink); }
.ck-hint { font-size: var(--oj-fs-md); }
.ck-btn {
  margin-top: auto;
  height: 42px;
  border: 0;
  border-radius: var(--oj-r2);
  background: var(--oj-accent);
  color: #fff;
  font-family: inherit;
  font-size: var(--oj-fs-lg);
  font-weight: 600;
  cursor: pointer;
  transition: background-color var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-1) var(--oj-ease);
}
.ck-btn:hover:not(:disabled) { background: var(--oj-accent-deep); }
.ck-btn:active:not(:disabled) { transform: translateY(1px); }
.ck-btn:disabled { opacity: 0.6; cursor: default; }
.ck-done {
  margin-top: auto;
  height: 42px;
  display: grid;
  place-items: center;
  border: 1px dashed var(--oj-line-strong);
  border-radius: var(--oj-r2);
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-md);
}

/* ------------------------------------------------------------- 区块骨架 */
.sec { margin-top: var(--oj-s6); }
.sec-head {
  display: flex;
  align-items: baseline;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  margin-bottom: var(--oj-s4);
  border-bottom: 1px solid var(--oj-line);
}
.sec-head h3 { font-size: var(--oj-fs-lg); }
.sec-head .spacer { flex: 1; }

/* ------------------------------------------------------------- 快捷入口 */
.entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--oj-s3);
}
.entry {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  padding: var(--oj-s4);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              background-color var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.entry:hover {
  border-color: var(--oj-ink-3);
  background: var(--oj-surface-2);
  transform: translateY(-1px);
}
.entry:active { transform: none; }
.entry-name { font-size: var(--oj-fs-lg); font-weight: 600; color: var(--oj-ink); }
.entry-desc { font-size: var(--oj-fs-sm); color: var(--oj-ink-3); }

/* ------------------------------------------------------------- 最新题目 */
.latest-list {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  overflow: hidden;
}
.latest-row {
  display: flex;
  align-items: center;
  gap: var(--oj-s3);
  padding: 10px var(--oj-s4);
  border-bottom: 1px solid var(--oj-line-soft);
  cursor: pointer;
  transition: background-color var(--oj-dur-1) var(--oj-ease);
}
.latest-row:last-child { border-bottom: none; }
.latest-row:hover { background: var(--oj-surface-2); }
.latest-id { min-width: 52px; font-size: var(--oj-fs-sm); color: var(--oj-ink-4); }
.latest-title {
  flex: 1;
  min-width: 0;
  font-size: var(--oj-fs-md);
  color: var(--oj-ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .hero { grid-template-columns: minmax(0, 1fr); }
  .checkin-panel { min-height: 0; }
  .ck-btn, .ck-done { margin-top: var(--oj-s2); }
}
@media (prefers-reduced-motion: reduce) {
  .entry, .latest-row, .ck-btn { transition: none; }
}
</style>
