<!--
  ProblemDetailView.vue - 题目详情页（刷题主入口，参考牛客 OJ 左右分栏布局）
  左侧：题面（Markdown + KaTeX + 样例）/「我的提交」两个 Tab，可折叠；
        我的提交 = 本人本题的提交记录，行点进 /submissions/:id 详情看代码与测试点
  右侧：引用统一编辑器工作台 CodeWorkbench（语言/编辑器/自测/提交/结果）
-->
<template>
  <div v-loading="loading" class="problem-page">
    <template v-if="problem">
      <div class="split">
        <!-- 左：题面 / 我的提交 -->
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
              <!-- 标签（点击跳列表页并按该标签筛选） -->
              <el-tag v-for="t in problem.tags ?? []" :key="t" size="small" effect="plain" type="info"
                      class="problem-tag"
                      @click.stop="$router.push({ path: '/problems', query: { tag: t } })">
                {{ t }}
              </el-tag>
              <!-- AI 助教入口：带题目上下文打开抽屉并预填（组件内自判登录态；登录才显示） -->
              <el-button v-if="userStore.isLoggedIn" size="small" text class="ask-ai-btn"
                         @click.stop="askAi">
                <el-icon style="margin-right:2px"><MagicStick /></el-icon>问 AI
              </el-button>
            </span>
          </div>
          <div v-show="!descCollapsed" class="pane-body">
            <!-- 题面 / 我的提交 切换（做题时直接回看本人本题提交代码；仅登录可见） -->
            <el-radio-group v-if="userStore.isLoggedIn" v-model="leftTab" size="small"
                            class="left-tabs" @change="onLeftTab">
              <el-radio-button :value="'desc'">题面</el-radio-button>
              <el-radio-button :value="'mysub'">我的提交</el-radio-button>
            </el-radio-group>

            <div v-show="leftTab === 'desc'">
              <p class="limits">时间限制 {{ problem.time_limit_ms }}ms ｜ 内存限制 {{ problem.memory_limit_mb }}MB</p>
              <div class="markdown" v-html="renderedDescription"></div>

            <!-- 样例（后端 is_sample=true 的用例，隐藏用例不下发） -->
            <template v-if="problem.samples?.length">
              <h4 class="samples-title">样例</h4>
              <div v-for="(s, i) in problem.samples" :key="i" class="sample-block">
                <div class="sample-io">
                  <div class="sample-label">
                    输入 #{{ Number(i) + 1 }}
                    <el-tooltip content="复制到自测运行的标准输入" placement="top">
                      <el-icon class="copy-icon" @click="copyText(s.input)"><CopyDocument /></el-icon>
                    </el-tooltip>
                  </div>
                  <pre class="sample-pre">{{ s.input || '（空）' }}</pre>
                </div>
                <div class="sample-io">
                  <div class="sample-label">输出 #{{ Number(i) + 1 }}</div>
                  <pre class="sample-pre">{{ s.output || '（空）' }}</pre>
                </div>
              </div>
            </template>
            </div>

            <!-- 我的提交：本人本题的提交记录，点行进详情页看代码与测试点 -->
            <div v-show="leftTab === 'mysub'" class="my-sub">
              <div class="my-sub-head">
                <span>我的提交（最多 50 条）</span>
                <el-button link type="primary" size="small"
                           @click="$router.push(`/submissions?problem=${problem.id}`)">
                  到提交记录页查看
                </el-button>
              </div>
              <el-table :data="mySubs" v-loading="subsLoading" size="small" class="click-table"
                        @row-click="(row: any) => $router.push(`/submissions/${row.id}`)">
                <el-table-column label="ID" width="100">
                  <template #default="{ row }">
                    <span class="mono-id" :title="row.id">{{ shortId(row.id) }}</span>
                  </template>
                </el-table-column>
                <el-table-column prop="language" label="语言" width="90" />
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag size="small" :type="statusTag(row.status)">{{ row.status_label }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="score" label="分" width="50" />
                <el-table-column label="用时/内存" min-width="110">
                  <template #default="{ row }">{{ row.time_ms }}ms · {{ (row.memory_kb / 1024).toFixed(1) }}MB</template>
                </el-table-column>
                <el-table-column label="时间" width="150">
                  <template #default="{ row }">{{ fmtTime(row.submitted_at) }}</template>
                </el-table-column>
              </el-table>
              <el-empty v-if="!subsLoading && !mySubs.length" description="本题还没有提交过" :image-size="60" />
            </div>
          </div>
        </div>

        <!-- 右：统一编辑器工作台 -->
        <div class="pane pane-right">
          <CodeWorkbench ref="workbenchRef" v-model:code="code" v-model:language="language"
                         :problem-id="problem.id" :auto-reset-on-lang-change="true"
                         :result="lastResult" @submit="submit" />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CaretLeft, CaretRight, CopyDocument, MagicStick } from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { api } from '../api/client'
import { shortId } from '../utils/format'
import { useUserStore } from '../stores/user'
import { useAssistantStore } from '../stores/assistant'
import CodeWorkbench from '../components/CodeWorkbench.vue'

const route = useRoute()
const userStore = useUserStore()
const assistant = useAssistantStore()
const problem = ref<any>(null)
const loading = ref(true)
const descCollapsed = ref(false)
const language = ref('python3.12')
const code = ref('')
const lastResult = ref<any>(null)

// 左侧「题面 / 我的提交」切换；我的提交 = 本人对本题的提交记录
const leftTab = ref<'desc' | 'mysub'>('desc')
const mySubs = ref<any[]>([])
const subsLoading = ref(false)
const subsLoaded = ref(false)

const statusTag = (s: string) =>
  ({ ac: 'success', wa: 'danger', tle: 'warning', mle: 'warning',
     re: 'danger', ce: 'info', se: 'danger', waiting: 'info', judging: 'info' }[s] ?? 'info') as any

const fmtTime = (s: string) => (s ? s.replace('T', ' ').slice(0, 16) : '')

async function loadMySubs() {
  if (!userStore.isLoggedIn || !problem.value) return
  subsLoading.value = true
  try {
    mySubs.value = await api.get('/submissions', {
      params: { problem_id: problem.value.id },
    }) as any
    subsLoaded.value = true
  } catch { /* 未登录等场景忽略 */ } finally {
    subsLoading.value = false
  }
}

function onLeftTab(v: any) {
  // 首次切到「我的提交」才拉取；提交完成后再次切回时刷新
  if (v === 'mysub' && !subsLoaded.value) loadMySubs()
}

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

const renderedDescription = computed(() =>
  problem.value ? md.render(problem.value.description ?? '') : '')

// 工作台引用：复制样例输入时预填自测面板 stdin（透出 setStdin）
const workbenchRef = ref<InstanceType<typeof CodeWorkbench> | null>(null)
function copyText(text: string) {
  workbenchRef.value?.setStdin(text ?? '')
  ElMessage.success('已复制到自测运行的标准输入')
}

// 「问 AI」：以本题为上下文打开助教抽屉（display_id 供后端 _resolve_context 与 get_hint 用）
function askAi() {
  assistant.openWithContext(
    { type: 'problem', problem_id: problem.value.id, display_id: problem.value.display_id },
    `我想了解 #${problem.value.display_id} ${problem.value.title} 的思路`)
}

onMounted(async () => {
  try {
    problem.value = await api.get(`/problems/${route.params.id}`)
    code.value = ''
  } catch {
    ElMessage.error('题目不存在')
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
    lastResult.value = await api.post('/submissions', {
      problem_id: problem.value.id,
      language: language.value,
      code: code.value,
    }) as any
    // 新提交后刷新「我的提交」列表（已加载过的话）
    if (subsLoaded.value) loadMySubs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '提交失败')
  }
}
</script>

<style scoped>
/* 页面占满整个内容区（App 布局已占满视口），内部分栏各自滚动 */
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

.pane-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}
.limits { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 0; }

/* 左侧「题面 / 我的提交」切换 */
.left-tabs { margin-bottom: 12px; }
.my-sub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.click-table :deep(tbody tr) { cursor: pointer; }
.mono-id {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: nowrap;
}
/* 题目标签：可点击跳列表筛选 */
.problem-tag { cursor: pointer; margin-left: 6px; }

/* 样例展示 */
.samples-title { margin: 18px 0 8px; }
.sample-block { margin-bottom: 12px; }
.sample-io { margin-bottom: 8px; }
.sample-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.copy-icon { cursor: pointer; }
.copy-icon:hover { color: var(--el-color-primary); }
.sample-pre {
  margin: 0;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 200px;
  overflow-y: auto;
}
</style>
