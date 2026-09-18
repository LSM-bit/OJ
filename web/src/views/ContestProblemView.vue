<!--
  ContestProblemView.vue - 比赛内题目页
  路由 /contests/:id/problems/:alias
  权限：ContestAccess("view") 校验比赛可见；私有题目不校验题目本身权限（比赛间接授权）
  布局复用左右分栏：左题面 / 右统一编辑器工作台 CodeWorkbench，提交走比赛内提交接口
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
                {{ alias }}. {{ problem.display_id }}. {{ problem.title }}
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
                         :problem-id="problem.id" :contest-id="contestId"
                         :auto-reset-on-lang-change="true" :result="lastResult"
                         not-logged-in-tip="请先登录并报名后再提交" @submit="submit">
            <template #head-left>
              <el-button size="small" text @click="$router.push(`/contests/${contestId}`)">
                ← 返回比赛
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

const contestId = computed(() => route.params.id as string)
const alias = computed(() => route.params.alias as string)

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
    // 比赛详情接口已带题目 id；比赛间接授权，直接取题目详情（带 contest_id）
    const contest = await api.get(`/contests/${contestId.value}`) as any
    const cp = contest.problems.find((p: any) => p.alias === alias.value)
    if (!cp) {
      ElMessage.error('该题目不在比赛中')
      return
    }
    problem.value = await api.get(`/problems/${cp.problem_id}?contest_id=${contestId.value}`)
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
    // 比赛内提交走比赛路由（后端校验报名/比赛时间，隐藏测试点细节）
    lastResult.value = await api.post(
      `/contests/${contestId.value}/problems/${alias.value}/submit`,
      { language: language.value, code: code.value }) as any
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
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  overflow: hidden;
}
.pane-left { flex: 1; min-width: 320px; }
.pane-left.collapsed { flex: 0 0 48px; min-width: 48px; }
.pane-right { flex: 1; min-width: 420px; }

.pane-head {
  flex-shrink: 0;
  padding: 10px 16px;
  border-bottom: 1px solid var(--oj-line-soft);
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

.pane-body { flex: 1; overflow-y: auto; padding: 12px 16px; }
.limits { color: var(--oj-ink-3); font-size: 13px; margin-top: 0; }
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

/* 题面/竞赛的左右分栏 */
.pane-head {
  padding: var(--oj-s3) var(--oj-s4);
  border-bottom: 1px solid var(--oj-line);
}
.pane-body { padding: var(--oj-s4) var(--oj-s5); }
.limits {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-sm);
  color: var(--oj-ink-3);
}
.sample-block {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
  overflow: hidden;
  transition: border-color var(--oj-dur-2) var(--oj-ease);
}
.sample-block:hover { border-color: var(--oj-line-strong); }
.samples-title,
.sample-label {
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--oj-ink-4);
}
.sample-pre { font-family: var(--oj-font-mono); }
</style>
