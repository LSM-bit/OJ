<!--
  CodeWorkbench.vue - 统一编辑器工作台组件
  封装做题页右栏的完整结构：语言选择 + 代码模板/重置 + Monaco 编辑器
  + 自测面板（SelfTestPanel）+ 提交动作 + 提交结果条
  供四个页面复用：题目详情 / 比赛内做题 / 题单内做题 / 验题（出题第 3 步）
  页面差异通过 props 配置 + 插槽扩展：
    #head-left      头部左侧（如"返回比赛"按钮）
    #head-after-lang 语言选择右侧（如验题页"已通过验证"标签）
    #head-right     头部右侧（默认重置+提交按钮，验题页换成"运行测试"）
    #footer         底部（默认提交结果条，验题页换成验证结果表格）
-->
<template>
  <div class="workbench">
    <!-- 头部：语言选择 + 插槽 + 默认重置/提交 -->
    <div class="wb-head">
      <slot name="head-left" />
      <el-select v-model="langModel" size="small" style="width:160px">
        <el-option label="Python 3.12" value="python3.12" />
        <el-option label="C++17" value="cpp17" />
        <el-option label="C17" value="c17" />
        <el-option label="Java 21" value="java21" />
      </el-select>
      <slot name="head-after-lang" />
      <div class="head-spacer" />
      <slot name="head-right">
        <el-button v-if="showReset" size="small" @click="resetCode">重置</el-button>
        <el-button v-if="showSubmit && userStore.isLoggedIn" type="primary" size="small"
                   :loading="submitting" @click="emit('submit')">
          {{ submitLabel }}
        </el-button>
      </slot>
    </div>

    <!-- 编辑器区：需要提交而未登录时给提示 -->
    <div class="editor-wrap">
      <el-alert v-if="showSubmit && !userStore.isLoggedIn" type="warning" :closable="false"
                :title="notLoggedInTip" show-icon style="margin:12px" />
      <CodeEditor v-else v-model="codeModel" :language="langModel" class="editor" />
    </div>

    <!-- 自测面板（公共组件）：stdin 输入 + 运行输出 -->
    <SelfTestPanel v-if="showSelfTest" ref="selftestRef" :problem-id="problemId"
                   :language="langModel" :code="codeModel"
                   :playlist-id="playlistId" :contest-id="contestId" />

    <!-- 底部：默认提交结果条 -->
    <slot name="footer">
      <div v-if="result" class="result-bar" :class="result.status">
        <span class="result-status">{{ result.status_label }}</span>
        <span class="result-meta">
          得分 {{ result.score }} ｜ 耗时 {{ result.time_ms }}ms
          <template v-if="showMemory">｜ 内存 {{ (result.memory_kb / 1024).toFixed(1) }}MB</template>
        </span>
      </div>
    </slot>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useUserStore } from '../stores/user'
import CodeEditor from './CodeEditor.vue'
import SelfTestPanel from './SelfTestPanel.vue'

const props = withDefaults(defineProps<{
  code: string
  language: string
  problemId?: string
  playlistId?: string
  contestId?: string
  showSelfTest?: boolean
  showSubmit?: boolean
  showReset?: boolean
  submitting?: boolean
  submitLabel?: string
  notLoggedInTip?: string
  result?: any | null
  showMemory?: boolean
  /** 切换语言时是否自动套用该语言模板（做题页 true，验题页 false 防覆盖标程） */
  autoResetOnLangChange?: boolean
}>(), {
  showSelfTest: true,
  showSubmit: true,
  showReset: true,
  submitting: false,
  submitLabel: '提交',
  notLoggedInTip: '请先登录后再提交',
  result: null,
  showMemory: true,
  autoResetOnLangChange: false,
})

const emit = defineEmits<{
  (e: 'update:code', value: string): void
  (e: 'update:language', value: string): void
  (e: 'submit'): void
}>()

const userStore = useUserStore()

// v-model 双向绑定
const codeModel = computed({
  get: () => props.code,
  set: (v: string) => emit('update:code', v),
})
const langModel = computed({
  get: () => props.language,
  set: (v: string) => emit('update:language', v),
})

// 按语言给一份模板代码（挂在组件内部，各页面不再重复维护）
const TEMPLATES: Record<string, string> = {
  'python3.12': '# 在此写入你的 Python 代码\n',
  cpp17: '#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    \n    return 0;\n}\n',
  c17: '#include <stdio.h>\n\nint main() {\n    \n    return 0;\n}\n',
  java21: 'import java.util.Scanner;\n\npublic class Main {\n    public static void main(String[] args) {\n        \n    }\n}\n',
}

function resetCode() {
  codeModel.value = TEMPLATES[langModel.value] ?? ''
}

// 挂载时先填模板，让编辑器不是空白
onMounted(resetCode)

// 部分页面（题目详情）切语言自动换模板；验题页关闭防覆盖已加载的标程
watch(langModel, () => {
  if (props.autoResetOnLangChange) resetCode()
})

// 自测面板引用：向父组件透出 setStdin（题目详情页复制样例输入用）
const selftestRef = ref<InstanceType<typeof SelfTestPanel> | null>(null)
function setStdin(text: string) {
  selftestRef.value?.setStdin(text ?? '')
}
// reset：向父组件透出「重置为当前语言模板」，供自定义 head-right 插槽的页面（验题页）挂重置按钮
defineExpose({ setStdin, reset: resetCode })
</script>

<style scoped>
.workbench {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.wb-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
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
