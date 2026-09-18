<!--
  AdminLogs.vue - 后台运行日志查看：API 进程内存环形缓冲（网关/HTTP 错误/业务日志）
  功能：级别筛选 + 关键词搜索 + 5s 自动刷新 + 游标加载更多 + 详情弹窗（含异常栈）+ 清空
  说明：日志随进程重启清空，定位"现在正在发生什么"；历史留存仍看 docker logs / 部署日志
-->
<template>
  <div class="page">
    <div class="toolbar">
      <el-radio-group v-model="level" @change="reload">
        <el-radio-button value="">全部</el-radio-button>
        <el-radio-button value="error">错误</el-radio-button>
        <el-radio-button value="warning">警告</el-radio-button>
        <el-radio-button value="info">信息</el-radio-button>
      </el-radio-group>
      <el-input v-model="q" placeholder="搜索消息 / 模块名，回车筛选" clearable style="width: 260px"
                @keyup.enter="reload" @clear="reload" />
      <div class="badges">
        <el-tag type="danger" effect="plain" size="small">错误 {{ stats.error }}</el-tag>
        <el-tag type="warning" effect="plain" size="small">警告 {{ stats.warning }}</el-tag>
        <el-tag type="info" effect="plain" size="small">信息 {{ stats.info }}</el-tag>
      </div>
      <div class="spacer" />
      <span class="auto-wrap">
        自动刷新
        <el-switch v-model="autoRefresh" size="small" />
      </span>
      <el-button :loading="loading" @click="reload">刷新</el-button>
      <el-button type="danger" plain @click="clearAll">清空</el-button>
    </div>

    <div class="log-list" v-loading="loading">
      <el-empty v-if="!loading && items.length === 0" description="暂无日志（缓冲为空或无匹配记录）" />
      <div v-for="e in items" :key="e.id" class="log-row" :class="rowClass(e.level)" @click="openDetail(e)">
        <span class="log-time">{{ formatTime(e.ts) }}</span>
        <el-tag :type="tagType(e.level)" size="small" effect="dark" class="log-level">
          {{ e.level }}
        </el-tag>
        <span class="log-name">{{ e.logger }}</span>
        <span class="log-msg">{{ e.message }}</span>
        <span v-if="e.exc" class="log-exc-mark">栈</span>
      </div>

      <div v-if="hasMore" class="load-more">
        <el-button text :loading="loadingMore" @click="loadMore">加载更早的日志</el-button>
      </div>
      <div v-else-if="items.length" class="load-more muted">已到最早记录</div>
    </div>

    <el-dialog v-model="detailVisible" title="日志详情" width="720">
      <div v-if="detail" class="detail">
        <div class="detail-meta">
          <el-tag :type="tagType(detail.level)" effect="dark">{{ detail.level }}</el-tag>
          <span class="muted">{{ detail.logger }}</span>
          <span class="muted">{{ detail.ts }}</span>
          <span class="muted">#{{ detail.id }}</span>
        </div>
        <pre class="detail-msg">{{ detail.message }}</pre>
        <template v-if="detail.exc">
          <div class="exc-title">异常栈</div>
          <pre class="detail-exc">{{ detail.exc }}</pre>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'

const items = ref<any[]>([])
const stats = ref({ info: 0, warning: 0, error: 0 })
const hasMore = ref(false)
const level = ref('')
const q = ref('')
const loading = ref(false)
const loadingMore = ref(false)
const autoRefresh = ref(true)
const detailVisible = ref(false)
const detail = ref<any>(null)

async function fetchPage(before?: number) {
  return await api.get('/admin/logs', {
    params: { level: level.value, q: q.value.trim(), before, limit: 200 },
  }) as any
}

async function reload() {
  loading.value = true
  try {
    const r = await fetchPage()
    items.value = r.items ?? []
    stats.value = r.stats ?? { info: 0, warning: 0, error: 0 }
    hasMore.value = !!r.has_more
  } catch {
    // 轮询静默失败不打扰；手动刷新有 loading 兜底
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (!items.value.length) return
  loadingMore.value = true
  try {
    const oldest = items.value[items.value.length - 1].id
    const r = await fetchPage(oldest)
    items.value.push(...(r.items ?? []))
    hasMore.value = !!r.has_more
  } finally {
    loadingMore.value = false
  }
}

function openDetail(e: any) {
  detail.value = e
  detailVisible.value = true
}

async function clearAll() {
  try {
    await ElMessageBox.confirm('清空内存中的运行日志？（进程重启后本就会清空）', '清空日志',
      { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' })
  } catch { return }
  const r = await api.delete('/admin/logs') as any
  ElMessage.success(`已清空 ${r.cleared ?? 0} 条`)
  reload()
}

// 5s 自动刷新（仅刷新第一页；用户翻到"加载更多"区域时暂停，避免列表跳动）
let timer: number | undefined
onMounted(() => {
  reload()
  timer = window.setInterval(() => {
    if (autoRefresh.value && !detailVisible.value) reload()
  }, 5000)
})
onUnmounted(() => clearInterval(timer))

function tagType(lv: string): 'danger' | 'warning' | 'info' {
  if (lv === 'ERROR' || lv === 'CRITICAL') return 'danger'
  if (lv === 'WARNING') return 'warning'
  return 'info'
}
function rowClass(lv: string) {
  return {
    'row-error': lv === 'ERROR' || lv === 'CRITICAL',
    'row-warning': lv === 'WARNING',
  }
}
function formatTime(ts: string) {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
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
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.spacer { flex: 1; }
.badges { display: flex; gap: 6px; }
.auto-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.log-list {
  flex: 1;
  overflow-y: auto;
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 6px 0;
}
.log-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 4px 14px;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12.5px;
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-extra-light);
}
.log-row:hover { background: var(--el-fill-color-light); }
.row-error { background: var(--el-color-danger-light-9); }
.row-warning { background: var(--el-color-warning-light-9); }
.log-time { color: var(--el-text-color-secondary); flex-shrink: 0; }
.log-level { flex-shrink: 0; }
.log-name {
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.log-msg {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--el-text-color-primary);
}
.log-exc-mark {
  flex-shrink: 0;
  color: var(--el-color-danger);
  font-weight: 700;
  font-size: 11px;
}
.load-more { text-align: center; padding: 8px 0; }
.muted { color: var(--el-text-color-secondary); }
.detail-meta { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.detail-msg, .detail-exc {
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 12px;
  font-size: 12.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 40vh;
  overflow-y: auto;
}
.exc-title { margin: 12px 0 6px; font-weight: 600; color: var(--el-color-danger); }
.detail-exc { background: var(--el-color-danger-light-9); }
</style>
