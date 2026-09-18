<!--
  CodeEditor.vue - Monaco 代码编辑器封装组件
  双向绑定 code（v-model），支持语言切换、主题跟随
-->
<template>
  <div ref="container" class="monaco-container"></div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor'

const props = defineProps<{
  modelValue: string
  language: string
  height?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const container = ref<HTMLElement | null>(null)
let editor: monaco.editor.IStandaloneCodeEditor | null = null

// monaco worker：vite 官方推荐写法，用 ?worker 构造器引入
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
self.MonacoEnvironment = {
  getWorker() {
    return new EditorWorker()
  },
}

// OJ 语言 id 映射到 monaco 语言
const LANG_MAP: Record<string, string> = {
  'python3.12': 'python',
  cpp17: 'cpp',
  c17: 'c',
  java21: 'java',
}

onMounted(() => {
  editor = monaco.editor.create(container.value!, {
    value: props.modelValue,
    language: LANG_MAP[props.language] ?? 'plaintext',
    theme: 'vs',
    minimap: { enabled: false },
    fontSize: 14,
    lineNumbers: 'on',
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 4,
    readOnly: props.readonly ?? false,
  })
  editor.onDidChangeModelContent(() => {
    emit('update:modelValue', editor!.getValue())
  })
})

watch(
  () => props.language,
  (lang) => {
    const model = editor?.getModel()
    if (model) monaco.editor.setModelLanguage(model, LANG_MAP[lang] ?? 'plaintext')
  },
)

watch(
  () => props.modelValue,
  (val) => {
    if (editor && editor.getValue() !== val) editor.setValue(val)
  },
)

onBeforeUnmount(() => {
  editor?.dispose()
})
</script>

<style scoped>
.monaco-container {
  width: 100%;
  height: 100%;
  min-height: 120px;
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
  overflow: hidden;
}
</style>
