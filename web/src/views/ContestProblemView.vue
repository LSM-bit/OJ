<!--
  ContestProblemView.vue - 比赛内题目页
  路由 /contests/:id/problems/:alias
  权限：ContestAccess("view") 校验比赛可见；私有题目不校验题目本身权限（比赛间接授权）
  布局复用题目详情页的左右分栏：左题面 / 右编辑器，提交走比赛内提交接口
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
              {{ contestId ? `${alias}. ` : '' }}{{ problem.display_id }}. {{ problem.title }}
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

        <!-- 右：编辑器 -->
        <div class="pane pane-right">
          <div class="pane-head editor-head">
            <el-button size="small" text @click="$router.push(`/contests/${contestId}`)">
              ← 返回比赛
            </el-button>
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
                      title="请先登录并报名后再提交" show-icon style="margin:12px" />
            <CodeEditor v-else v-model="code" :language="language" class="editor" />
          </div>

          <!-- 自测面板（公共组件）：stdin 输入 + 运行输出，不计入比赛成绩 -->
          <SelfTestPanel :problem-id="problem.id" :language="language" :code="code"
                         :contest-id="contestId" />

          <div v-if="lastResult" class="result-bar" :class="lastResult.status">
            <span class="result-status">{{ lastResult.status_label }}</span>
            <span class="result-meta">
              得分 {{ lastResult.score }} ｜ 耗时 {{ lastResult.time_ms }}ms
            </span>
          </div>
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
import { useUserStore } from '../stores/user'
import CodeEditor from '../components/CodeEditor.vue'
import SelfTestPanel from '../components/SelfTestPanel.vue'

const route = useRoute()
const userStore = useUserStore()

const contestId = computed(() => route.params.id as string)
const alias = computed(() => route.params.alias as string)

const problem = ref<any>(null)
const loading = ref(true)
const descCollapsed = ref(false)
const language = ref('python3.12')
const code = ref('')
const submitting = ref(false)
const lastResult = ref<any>(null)

const renderedDescription = computed(() =>
  problem.value ? md.render(problem.value.description ?? '') : '')

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

const TEMPLATES: Record<string, string> = {
  'python3.12': '# 在此写入你的 Python 代码\n',
  cpp17: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    \n    return 0;\n}\n',
  c17: '#include <stdio.h>\n\nint main() {\n    \n    return 0;\n}\n',
  java21: 'import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        \n    }\n}\n',
}

function resetCode() {
  code.value = TEMPLATES[language.value] ?? ''
}

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
    resetCode()
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
  submitting.value = true
  try {
    // 比赛内提交走比赛路由（后端校验报名/比赛时间，隐藏测试点细节）
    lastResult.value = await api.post(
      `/contests/${contestId.value}/problems/${alias.value}/submit`,
      { language: language.value, code: code.value }) as any
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '提交失败')
  } finally {
    submitting.value = false
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
.pane-left.collapsed .pane-title { writing-mode: vertical-lr; display: inline-block; }
.pane-title { cursor: pointer; }

.pane-body { flex: 1; overflow-y: auto; padding: 12px 16px; }
.limits { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 0; }

.editor-head { display: flex; align-items: center; gap: 8px; }
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
