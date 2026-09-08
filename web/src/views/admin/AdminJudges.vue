<!--
  AdminJudges.vue - 后台判题节点监控：节点卡片（在线/容量/占用/心跳）+ 队列深度
-->
<template>
  <div class="page">
    <div class="head">
      <h2 class="page-title">判题节点监控</h2>
      <div class="queue-info">
        <el-tag type="info" size="large">等待队列：{{ snap.queue_length ?? 0 }}</el-tag>
        <el-tag type="info" size="large">进行中：{{ snap.pending_count ?? 0 }}</el-tag>
      </div>
    </div>

    <el-empty v-if="!loading && nodes.length === 0" description="暂无节点注册" />

    <div class="node-grid">
      <div v-for="n in nodes" :key="n.node_id" class="node-card">
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { api } from '../../api/client'

const snap = ref<any>({})
const nodes = ref<any[]>([])
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
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
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
  color: var(--el-text-color-secondary);
  margin-bottom: 10px;
}
</style>
