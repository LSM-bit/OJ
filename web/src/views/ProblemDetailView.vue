<!--
  ProblemDetailView.vue - 题目详情页（参考牛客 OJ 左右分栏布局）
  左侧：题面（Markdown + KaTeX），可折叠
  右侧：Monaco 编辑器 + 语言选择 + 提交结果
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

        <!-- 右：编辑器 -->
        <div class="pane pane-right">
          <div class="pane-head editor-head">
            <el-select v-model="language" size="small" style="width:160px">
              <el-option label="Python 3.12" value="python3.12" />
              <el-option label="C++17" value="cpp17" />
              <el-option label="C17" value="c17" />
              <el-option label="Java 21" value="java21" />
            </el-select>
            <div class="head-spacer" />
            <el-button size="small" @click="resetCode">重置</el-button>
            <el-button v-if="userStore.isLoggedIn" type="primary" size="small"
                       :loading="submitting" @click="submit">提交</el-button>
          </div>

          <div class="editor-wrap">
            <el-alert v-if="!userStore.isLoggedIn" type="warning" :closable="false"
                      title="请先登录后再提交" show-icon style="margin:12px" />
            <CodeEditor v-else v-model="code" :language="language" class="editor" />
          </div>

          <!-- 自测面板（公共组件）：stdin 输入 + 运行输出 -->
          <SelfTestPanel ref="selftestRef" :problem-id="problem.id"
                         :language="language" :code="code" />

          <div v-if="lastResult" class="result-bar" :class="lastResult.status">
            <span class="result-status">{{ lastResult.status_label }}</span>
            <span class="result-meta">
              得分 {{ lastResult.score }} ｜ 耗时 {{ lastResult.time_ms }}ms ｜
              内存 {{ (lastResult.memory_kb / 1024).toFixed(1) }}MB
            </span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { CaretLeft, CaretRight } from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'
import CodeEditor from '../components/CodeEditor.vue'
import SelfTestPanel from '../components/SelfTestPanel.vue'

const route = useRoute()
const userStore = useUserStore()
const problem = ref<any>(null)
const loading = ref(true)
const descCollapsed = ref(false)
const language = ref('python3.12')
const code = ref('')
const submitting = ref(false)
const lastResult = ref<any>(null)

// 自测面板（公共组件）：复制样例输入时预填其 stdin
const selftestRef = ref<InstanceType<typeof SelfTestPanel> | null>(null)

// 复制样例输入到自测面板的标准输入
function copyText(text: string) {
  selftestRef.value?.setStdin(text ?? '')
  ElMessage.success('已复制到自测运行的标准输入')
}

const renderedDescription = computed(() =>
  problem.value ? md.render(problem.value.description ?? '') : '')

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

// 按语言给一份模板代码
const TEMPLATES: Record<string, string> = {
  'python3.12': '# 在此写入你的 Python 代码\n',
  cpp17: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    \n    return 0;\n}\n',
  c17: '#include <stdio.h>\n\nint main() {\n    \n    return 0;\n}\n',
  java21: 'import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        \n    }\n}\n',
}

function resetCode() {
  code.value = TEMPLATES[language.value] ?? ''
}

// 切换语言时自动套用对应语言的初始代码框架
watch(language, resetCode)

onMounted(async () => {
  try {
    problem.value = await api.get(`/problems/${route.params.id}`)
    resetCode()
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
  submitting.value = true
  try {
    lastResult.value = await api.post('/submissions', {
      problem_id: problem.value.id,
      language: language.value,
      code: code.value,
    })
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '提交失败')
  } finally {
    submitting.value = false
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

.editor-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.head-spacer { flex: 1; }

.editor-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 12px;
}
.editor { flex: 1; min-height: 0; }

.result-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  font-size: 13px;
}
.result-status { font-weight: 700; font-size: 14px; }
.result-bar.ac .result-status { color: var(--el-color-success); }
.result-bar.wa .result-status, .result-bar.re .result-status,
.result-bar.tle .result-status, .result-bar.mle .result-status { color: var(--el-color-danger); }
.result-bar.ce .result-status { color: var(--el-color-warning); }
.result-meta { color: var(--el-text-color-secondary); }
</style>
