<!--
  ContestsView.vue - 比赛列表页
  参考牛客 OJ 风格：卡片式比赛列表，展示赛制/状态/时间，支持报名跳转
  分类规则：比赛分「未结束」（含未开始/进行中/结束未满 24h）与
  「已结束（归档）」（结束满 24h 自动归档）两类，筛选按 archived 字段分桶；
  卡片标签仍显示细粒度阶段（进行中/未开始/已结束），归档的额外挂「已归档」标
-->
<template>
  <div v-loading="loading" class="page">
    <div class="page-head">
      <h2>比赛</h2>
      <div class="head-actions">
        <el-radio-group v-model="phaseFilter" size="small">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="open">未结束</el-radio-button>
          <el-radio-button value="archived">已结束（归档）</el-radio-button>
        </el-radio-group>
        <el-button v-if="userStore.isLoggedIn" type="primary" size="small"
                   @click="$router.push('/contests/new')">创建比赛</el-button>
      </div>
    </div>

    <el-empty v-if="!loading && filtered.length === 0" description="暂无比赛" />

    <div class="contest-list">
      <div v-for="c in filtered" :key="c.id" class="contest-card" @click="goDetail(c)">
        <div class="card-main">
          <div class="card-title-row">
            <el-tag :type="phaseTag(c.phase)" size="small" effect="dark">{{ phaseLabel(c.phase) }}</el-tag>
            <el-tag v-if="c.archived" type="info" size="small" effect="plain">已归档</el-tag>
            <el-tag v-if="!c.is_public" type="info" size="small" effect="plain">私有</el-tag>
            <span class="card-title">{{ c.title }}</span>
          </div>
          <p class="card-desc">{{ c.description || '暂无简介' }}</p>
          <div class="card-meta">
            <span>{{ fmtTime(c.start_at) }} ~ {{ fmtTime(c.end_at) }}</span>
            <span class="meta-divider">|</span>
            <span>{{ ruleLabel(c.rule) }}</span>
            <span class="meta-divider">|</span>
            <span v-if="c.board_freeze_minutes > 0">封榜 {{ c.board_freeze_minutes }} 分钟</span>
            <span v-else>不封榜</span>
          </div>
        </div>
        <div class="card-side">
          <el-button type="primary" plain size="small" @click.stop="goDetail(c)">进入</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const contests = ref<any[]>([])
const loading = ref(false)
const phaseFilter = ref('')

// 分类筛选：open=未结束（含结束未满 24h），archived=已结束（归档），''=全部
const filtered = computed(() => {
  if (phaseFilter.value === 'open') return contests.value.filter((c) => !c.archived)
  if (phaseFilter.value === 'archived') return contests.value.filter((c) => c.archived)
  return contests.value
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
.page-head h2 { margin: 0; }
.head-actions { display: flex; align-items: center; gap: 12px; }
.contest-list { display: flex; flex-direction: column; gap: 12px; }
.contest-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.contest-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}
.card-main { flex: 1; min-width: 0; }
.card-title-row { display: flex; align-items: center; gap: 10px; }
.card-title { font-size: 16px; font-weight: 600; color: var(--el-text-color-primary); }
.card-desc {
  margin: 8px 0;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-meta { color: var(--el-text-color-secondary); font-size: 12px; }
.meta-divider { margin: 0 8px; }
.card-side { flex-shrink: 0; }
</style>
