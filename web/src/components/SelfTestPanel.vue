<!--
  SelfTestPanel.vue - 自测运行面板（公共组件）
  用法：<SelfTestPanel :problem-id="problem.id" :language="language" :code="code" />
  功能：输入自定义 stdin，调用 /submissions/run 沙箱运行一次（不落库不计分），
        展示程序输出/错误与耗时内存。未登录不渲染。
  样例输入可通过 ref 暴露的 setStdin(text) 预填（题目详情页复制按钮用）。
-->
<template>
  <div v-if="userStore.isLoggedIn" class="selftest">
    <div class="selftest-tabs">
      <span class="selftest-title">自测运行</span>
      <el-button size="small" type="success" plain
                 :loading="running" @click="run">运行</el-button>
      <span v-if="runResult" class="selftest-meta">
        {{ runResult.status_label }} ｜ {{ runResult.time_used_ms }}ms ｜
        {{ (runResult.memory_used_kb / 1024).toFixed(1) }}MB
      </span>
    </div>
    <div class="selftest-body">
      <div class="selftest-col">
        <div class="selftest-label">标准输入（stdin）</div>
        <el-input v-model="stdinText" type="textarea" :rows="4" resize="none"
                  placeholder="运行时作为程序的标准输入" class="selftest-io" />
      </div>
      <div class="selftest-col">
        <div class="selftest-label">程序输出</div>
        <pre v-if="runResult" class="selftest-io" :class="{ err: isRunFailed }">{{ runResult.output || '（无输出）' }}<template v-if="runResult.error_message">{{ '\n' }}[stderr] {{ runResult.error_message }}</template></pre>
        <pre v-else class="selftest-io placeholder">点击「运行」后在此显示输出</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const props = defineProps<{
  problemId?: string | number  // 雪花 ID 用字符串透传，避免精度丢失；不传用默认限制
  language: string
  code: string
  playlistId?: string | number // 题单上下文：私有题经题单授权取题目限制
  contestId?: string | number  // 比赛上下文：同上
}>()

const userStore = useUserStore()
const running = ref(false)
const stdinText = ref('')
const runResult = ref<any>(null)
const isRunFailed = computed(() =>
  runResult.value && runResult.value.status !== 'finished')

// 供父组件预填样例输入（复制按钮）
function setStdin(text: string) {
  stdinText.value = text
}
defineExpose({ setStdin })

// 自测：沙箱运行一次，不落库不计分
async function run() {
  if (!props.code.trim()) {
    ElMessage.warning('代码不能为空')
    return
  }
  running.value = true
  runResult.value = null
  try {
    runResult.value = await api.post('/submissions/run', {
      problem_id: props.problemId,
      language: props.language,
      code: props.code,
      stdin: stdinText.value,
      playlist_id: props.playlistId,
      contest_id: props.contestId,
    })
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '运行失败')
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
/* 自测面板 */
.selftest {
  flex-shrink: 0;
  border-top: 1px solid var(--oj-line-soft);
  padding: 8px 12px 12px;
}
.selftest-tabs {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.selftest-title { font-size: 13px; font-weight: 600; }
.selftest-meta { font-size: 12px; color: var(--oj-ink-3); }
.selftest-body {
  display: flex;
  gap: 12px;
}
.selftest-col { flex: 1; min-width: 0; }
.selftest-label {
  font-size: 12px;
  color: var(--oj-ink-3);
  margin-bottom: 4px;
}
.selftest-io {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  height: 96px;
  max-height: 96px;
  overflow-y: auto;
  background: var(--oj-surface-2);
  border: 1px solid var(--oj-line-soft);
  border-radius: var(--oj-r2);
  padding: 6px 8px;
  box-sizing: border-box;
}
.selftest-io.err { color: var(--el-color-danger); }
.selftest-io.placeholder { color: var(--oj-ink-4); }
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

/* 工作台 / 自测面板 / 标签选择器 */
.workbench {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}
.wb-head { border-bottom: 1px solid var(--oj-line); }
.result-bar { border-top: 1px solid var(--oj-line); }
.selftest {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}
.selftest-tabs { border-bottom: 1px solid var(--oj-line); }
.selftest-io { font-family: var(--oj-font-mono); }
.result-item,
.result-item:hover {
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.result-item:hover { background: var(--oj-surface-2); }
.result-item { border-radius: var(--oj-r2); }
.picked { border-bottom: 1px solid var(--oj-line-soft); }
</style>
