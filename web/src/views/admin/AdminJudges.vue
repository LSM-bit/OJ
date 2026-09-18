<!--
  AdminJudges.vue - 后台判题节点监控：节点卡片（在线/容量/占用/心跳）+ 队列深度
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Admin</span>
        <h2>判题节点监控</h2>
      </div>
      <div class="queue-info">
        <el-tag type="info" size="large">等待队列：{{ snap.queue_length ?? 0 }}</el-tag>
        <el-tag type="info" size="large">进行中：{{ snap.pending_count ?? 0 }}</el-tag>
      </div>
    </header>

    <el-empty v-if="!loading && nodes.length === 0" description="暂无节点注册" />

    <div class="node-grid">
      <div v-for="n in pagedNodes" :key="n.node_id" class="node-card">
        <div class="node-head">
          <span class="node-name">{{ n.name || n.node_id }}</span>
          <el-tag size="small" :type="n.online ? 'success' : 'danger'">
            {{ n.online ? '在线' : '离线' }}
          </el-tag>
        </div>
        <div class="node-meta">
          <span>节点ID：{{ n.node_id }}</span>
          <span>容量占用：{{ n.running }} / {{ n.capacity }}</span>
          <span v-if="n.last_seen_seconds_ago != null">
            心跳：{{ n.last_seen_seconds_ago }}s 前
          </span>
        </div>
        <el-progress :percentage="Math.min(100, Math.round(n.running / Math.max(n.capacity, 1) * 100))"
                     :status="n.running >= n.capacity ? 'warning' : undefined" />
      </div>
    </div>
    <div v-if="nodesTotal > nodesPageSize" class="pager-row">
      <el-pagination class="pager" layout="total, prev, pager, next"
                     :total="nodesTotal" :page-size="nodesPageSize"
                     v-model:current-page="nodesPage" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api/client'
import { useClientPager } from '../../composables/useClientPager'

const snap = ref<any>({})
const nodes = ref<any[]>([])

// 判题节点扩容后卡片会变多：预留分页
const { page: nodesPage, size: nodesPageSize, total: nodesTotal, paged: pagedNodes } =
  useClientPager(computed<any[]>(() => nodes.value), 12)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    snap.value = await api.get('/admin/judges') as any
    nodes.value = snap.value.nodes ?? []
  } finally {
    loading.value = false
  }
}

// 5 秒轮询
let timer: number | undefined
onMounted(() => {
  load()
  timer = window.setInterval(load, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-title { margin: 0; }
.queue-info { display: flex; gap: 10px; }
.node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.node-card {
  padding: 14px 16px;
  background: var(--oj-surface);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
}
.node-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.node-name { font-weight: 600; }
.node-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: var(--oj-ink-3);
  margin-bottom: 10px;
}
/* ===== 视觉刷新：统一页面骨架（追加层，保证同特异性下胜出） ===== */
.page {
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
}
.page-head,
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.page-head h2,
.page-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s4);
}
.spacer { flex: 1; }
.mono-id,
.mono {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--oj-ink-3);
}
.muted,
.tip,
.pick-hint,
.form-tip,
.data-hint,
.err-msg {
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.section { margin-top: var(--oj-s6); }
.section h4 {
  margin: 0 0 var(--oj-s3);
  font-size: var(--oj-fs-lg);
}
.stat-card {
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.stat-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateY(-1px);
}
.stat-value {
  font-family: var(--oj-font-mono);
  font-size: 26px;
  letter-spacing: -0.02em;
  color: var(--oj-ink);
}
.stat-label {
  margin-top: 4px;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0;
}
.click-table,
.fill-table,
.cases-table,
.verify-table,
.log-list {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}

/* 管理后台 */
.admin-aside {
  background: var(--oj-surface-2);
  border-right: 1px solid var(--oj-line);
}
.admin-logo {
  font-family: var(--oj-font-display);
  letter-spacing: -0.01em;
}
.admin-logo,
.admin-back { border-bottom: 1px solid var(--oj-line-soft); }
.badges { display: flex; align-items: center; gap: var(--oj-s1); }
.log-list { background: var(--oj-surface); }
.log-row {
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.log-time { font-family: var(--oj-font-mono); color: var(--oj-ink-4); }
.node-card {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease);
}
.node-card:hover { border-color: var(--oj-line-strong); box-shadow: var(--oj-shadow-1); }
.chart {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
}
.rename-tip { color: var(--oj-ink-3); font-size: var(--oj-fs-sm); }
.preview {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: var(--oj-s3) var(--oj-s4);
}

/* ===== 逻辑复查：统一标题区与分页行 ===== */
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { margin: 0; font-size: 26px; letter-spacing: -0.02em; }
.head-ops { display: flex; align-items: center; gap: var(--oj-s2); flex-wrap: wrap; }
.pager-row { display: flex; justify-content: flex-end; padding: var(--oj-s3) 0; }
</style>
