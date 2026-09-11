<!--
  PlaylistProblemView.vue - 题单内题目页
  路由 /playlists/:id/problems/:pid
  权限链：PlaylistAccess("view")（后端）→ 题单详情校验该题 visible → 拉取题目详情
  布局复用左右分栏：左题面 / 右统一编辑器工作台 CodeWorkbench，
  提交走普通提交接口（题单无比赛时间/报名限制，带 playlist_id 上下文授权）
-->
<template>
  <div v-loading="loading" class="problem-page">
    <template v-if="problem">
      <div class="split">
        <!-- 左：题面 -->
        <div class="pane pane-left" :class="{ collapsed: descCollapsed }">
          <div class="pane-head">
            <span class="pane-title" @click="descCollapsed = !descCollapsed">
              <el-icon class="fold-icon">
                <CaretLeft v-if="!descCollapsed" />
                <CaretRight v-else />
              </el-icon>
              <span class="title-text">
                <span class="display-id">{{ problem.display_id }}</span>
                . {{ problem.title }}
              </span>
              <el-tag :type="diffTag(problem.difficulty)" size="small" style="margin-left:8px">
                {{ diffLabel(problem.difficulty) }}
              </el-tag>
            </span>
          </div>
          <div v-show="!descCollapsed" class="pane-body">
            <p class="limits">时间限制 {{ problem.time_limit_ms }}ms ｜ 内存限制 {{ problem.memory_limit_mb }}MB</p>
            <div class="markdown" v-html="renderedDescription"></div>
          </div>
        </div>

        <!-- 右：统一编辑器工作台 -->
        <div class="pane pane-right">
          <CodeWorkbench v-model:code="code" v-model:language="language"
                         :problem-id="problemId" :playlist-id="playlistId"
                         :auto-reset-on-lang-change="true" :result="lastResult"
                         @submit="submit">
            <template #head-left>
              <el-button size="small" text @click="$router.push(`/playlists/${playlistId}`)">
                ← 返回题单
              </el-button>
            </template>
          </CodeWorkbench>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CaretLeft, CaretRight } from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { api } from '../api/client'
import CodeWorkbench from '../components/CodeWorkbench.vue'

const route = useRoute()

const playlistId = computed(() => route.params.id as string)
const problemId = computed(() => route.params.pid as string)

const problem = ref<any>(null)
const loading = ref(true)
const descCollapsed = ref(false)
const language = ref('python3.12')
const code = ref('')
const lastResult = ref<any>(null)

const renderedDescription = computed(() =>
  problem.value ? md.render(problem.value.description ?? '') : '')

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  try {
    // 权限链：题单详情（后端 PlaylistAccess 校验题单可见）
    // → 确认该题在题单内 → 题目详情带 playlist_id 间接授权（可见性只看题单）
    const pl = await api.get(`/playlists/${playlistId.value}`) as any
    const item = (pl.problems ?? []).find((p: any) => String(p.problem_id) === problemId.value)
    if (!item) {
      ElMessage.error('该题目不在题单中')
      return
    }
    problem.value = await api.get(`/problems/${problemId.value}?playlist_id=${playlistId.value}`)
    code.value = ''
  } catch {
    ElMessage.error('题目不存在或无权访问')
  } finally {
    loading.value = false
  }
})

async function submit() {
  if (!code.value.trim()) {
    ElMessage.warning('代码不能为空')
    return
  }
  try {
    // 提交带 playlist_id：后端按题单可见性放行私有题
    // ID 保持字符串：雪花 ID 超出 Number 安全范围，Number() 会改写末几位
    lastResult.value = await api.post('/submissions', {
      problem_id: problemId.value,
      language: language.value,
      code: code.value,
      playlist_id: playlistId.value,
    }) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '提交失败')
  }
}
</script>

<style scoped>
.problem-page {
  height: 100%;
  padding: 12px;
  box-sizing: border-box;
}
.split {
  display: flex;
  gap: 12px;
  height: 100%;
}
.pane {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
}
.pane-left { flex: 1; min-width: 320px; }
.pane-left.collapsed { flex: 0 0 48px; min-width: 48px; }
.pane-right { flex: 1; min-width: 420px; }

.pane-head {
  flex-shrink: 0;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
  white-space: nowrap;
}
.fold-icon { vertical-align: -2px; cursor: pointer; }
/* 折叠后：只留窄条 + 居中的展开图标，不显示题名内容 */
.pane-left.collapsed .pane-head {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 10px 0;
  border-bottom: none;
}
.pane-left.collapsed .pane-title {
  cursor: pointer;
}
.pane-left.collapsed .title-text,
.pane-left.collapsed .el-tag {
  display: none;
}
.pane-title { cursor: pointer; }
.display-id {
  color: var(--el-color-primary);
  font-weight: 700;
}

.pane-body { flex: 1; overflow-y: auto; padding: 12px 16px; }
.limits { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 0; }
</style>
