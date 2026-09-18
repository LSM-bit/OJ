<!--
  ContestsView.vue - 比赛列表页
  参考牛客 OJ 风格：卡片式比赛列表，展示赛制/状态/时间，支持报名跳转
  分类规则：比赛分「未结束」（含未开始/进行中/结束未满 24h）与
  「已结束（归档）」（结束满 24h 自动归档）两类，筛选按 archived 字段分桶；
  卡片标签仍显示细粒度阶段（进行中/未开始/已结束），归档的额外挂「已归档」标
-->
<template>
  <div v-loading="loading" class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Contests</span>
        <h2>竞赛</h2>
      </div>
      <div class="head-actions">
        <el-radio-group v-model="phaseFilter" size="small" @change="resetPage">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="open">未结束</el-radio-button>
          <el-radio-button value="archived">已归档</el-radio-button>
        </el-radio-group>
        <el-button v-if="userStore.isLoggedIn" type="primary" size="small"
                   @click="$router.push('/contests/new')">创建竞赛</el-button>
      </div>
    </header>

    <el-empty v-if="!loading && filtered.length === 0" description="暂无比赛" />

    <div class="contest-list">
      <article v-for="c in pagedContests" :key="c.id" class="contest-card"
               :data-phase="c.phase" @click="goDetail(c)">
        <div class="card-main">
          <div class="card-title-row">
            <el-tag :type="phaseTag(c.phase)" size="small" effect="plain">
              {{ phaseLabel(c.phase) }}
            </el-tag>
            <span class="card-title">{{ c.title }}</span>
            <el-tag v-if="c.archived" type="info" size="small" effect="plain">已归档</el-tag>
            <el-tag v-if="!c.is_public" type="info" size="small" effect="plain">私有</el-tag>
          </div>
          <p class="card-desc">{{ c.description || '暂无简介' }}</p>
          <div class="card-meta">
            <span class="mono">{{ fmtTime(c.start_at) }} → {{ fmtTime(c.end_at) }}</span>
            <span class="dot">·</span>
            <span>{{ ruleLabel(c.rule) }}</span>
            <span class="dot">·</span>
            <span>{{ c.board_freeze_minutes > 0 ? `封榜 ${c.board_freeze_minutes} 分钟` : '不封榜' }}</span>
          </div>
        </div>
        <span class="card-go">进入<i>→</i></span>
      </article>
    </div>

    <div class="pager-row">
      <el-pagination v-if="filtered.length > pageSize" class="pager"
                     layout="total, prev, pager, next"
                     :total="filtered.length" :page-size="pageSize"
                     v-model:current-page="page" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const contests = ref<any[]>([])
const loading = ref(false)
const phaseFilter = ref('')
// 客户端分页：接口返回全部可见比赛，页面内分页展示
const page = ref(1)
const pageSize = 8

function resetPage() {
  page.value = 1
}

// 分类筛选：open=未结束（含结束未满 24h），archived=已结束（归档），''=全部
const filtered = computed(() => {
  if (phaseFilter.value === 'open') return contests.value.filter((c) => !c.archived)
  if (phaseFilter.value === 'archived') return contests.value.filter((c) => c.archived)
  return contests.value
})

const pagedContests = computed(() =>
  filtered.value.slice((page.value - 1) * pageSize, page.value * pageSize))

// 切换筛选 / 列表变化时回到第一页，避免停留在空页
watch(phaseFilter, resetPage)
watch(filtered, () => {
  if ((page.value - 1) * pageSize >= filtered.value.length) page.value = 1
})

const phaseLabel = (p: string) => ({ running: '进行中', upcoming: '未开始', ended: '已结束' }[p] ?? p)
const phaseTag = (p: string) => ({ running: 'success', upcoming: 'warning', ended: 'info' }[p] ?? 'info') as any
const ruleLabel = (r: string) => ({ acm: 'ACM 赛制', oi: 'OI 赛制', ioi: 'IOI 赛制' }[r] ?? r)

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function goDetail(c: any) {
  router.push(`/contests/${c.id}`)
}

onMounted(async () => {
  loading.value = true
  try {
    contests.value = await api.get('/contests') as any
  } finally {
    loading.value = false
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
.head-actions { display: flex; align-items: center; gap: var(--oj-s3); }

.contest-list { display: flex; flex-direction: column; gap: var(--oj-s3); }
/* 卡片左侧一道细竖条承担状态信号，不再靠整块色标签抢注意力 */
.contest-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--oj-s5);
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  cursor: pointer;
  overflow: hidden;
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.contest-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--oj-line-strong);
}
.contest-card[data-phase='running']::before { background: var(--oj-ac); }
.contest-card[data-phase='upcoming']::before { background: var(--oj-warn); }
.contest-card[data-phase='ended']::before { background: var(--oj-ink-4); }
.contest-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateX(2px);
}

.card-main { flex: 1; min-width: 0; }
.card-title-row { display: flex; align-items: center; gap: var(--oj-s2); }
.card-title {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-xl);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--oj-ink);
}
.card-desc {
  margin: var(--oj-s2) 0 0;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-md);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta {
  margin-top: var(--oj-s3);
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.card-meta .mono {
  font-family: var(--oj-font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--oj-ink-2);
}
.dot { color: var(--oj-ink-4); }

.card-go {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding-left: var(--oj-s5);
  font-size: var(--oj-fs-md);
  color: var(--oj-ink-4);
  transition: color var(--oj-dur-2) var(--oj-ease);
}
.card-go i {
  font-style: normal;
  transition: transform var(--oj-dur-2) var(--oj-ease);
}
.contest-card:hover .card-go { color: var(--oj-accent); }
.contest-card:hover .card-go i { transform: translateX(3px); }

.pager-row {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s4) 0 0;
}
</style>
