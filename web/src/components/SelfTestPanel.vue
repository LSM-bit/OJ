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
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 8px 12px 12px;
}
.selftest-tabs {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.selftest-title { font-size: 13px; font-weight: 600; }
.selftest-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.selftest-body {
  display: flex;
  gap: 12px;
}
.selftest-col { flex: 1; min-width: 0; }
.selftest-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
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
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 6px 8px;
  box-sizing: border-box;
}
.selftest-io.err { color: var(--el-color-danger); }
.selftest-io.placeholder { color: var(--el-text-color-placeholder); }
</style>
