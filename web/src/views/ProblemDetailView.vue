<!--
  ProblemDetailView.vue - 题目详情页（刷题主入口，参考牛客 OJ 左右分栏布局）
  左侧：题面（Markdown + KaTeX + 样例），可折叠
  右侧：引用统一编辑器工作台 CodeWorkbench（语言/编辑器/自测/提交/结果）
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
              <!-- 标签（点击跳列表页并按该标签筛选） -->
              <el-tag v-for="t in problem.tags ?? []" :key="t" size="small" effect="plain" type="info"
                      class="problem-tag"
                      @click.stop="$router.push({ path: '/problems', query: { tag: t } })">
                {{ t }}
              </el-tag>
            </span>
          </div>
          <div v-show="!descCollapsed" class="pane-body">
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
import { CaretLeft, CaretRight, CopyDocument } from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { api } from '../api/client'
import CodeWorkbench from '../components/CodeWorkbench.vue'

const route = useRoute()
const problem = ref<any>(null)
const loading = ref(true)
const descCollapsed = ref(false)
const language = ref('python3.12')
const code = ref('')
const lastResult = ref<any>(null)

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
