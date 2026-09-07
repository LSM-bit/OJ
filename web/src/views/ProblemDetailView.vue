<template>
  <div v-loading="loading">
    <template v-if="problem">
      <h2>{{ problem.display_id }}. {{ problem.title }}
        <el-tag :type="diffTag(problem.difficulty)" size="small" style="margin-left:8px">
          {{ diffLabel(problem.difficulty) }}
        </el-tag>
      </h2>
      <p class="limits">时间限制 {{ problem.time_limit_ms }}ms ｜ 内存限制 {{ problem.memory_limit_mb }}MB</p>
      <el-card class="desc">
        <div class="markdown" v-html="renderedDescription"></div>
      </el-card>

      <h3>提交代码</h3>
      <el-alert v-if="!userStore.isLoggedIn" type="warning" :closable="false"
                title="请先登录后再提交" show-icon style="margin-bottom:12px" />
      <template v-else>
        <el-select v-model="language" style="width:200px; margin-bottom:12px">
          <el-option label="Python 3.12" value="python3.12" />
          <el-option label="C++17" value="cpp17" />
          <el-option label="C17" value="c17" />
          <el-option label="Java 21" value="java21" />
        </el-select>
        <el-input v-model="code" type="textarea" :rows="14" placeholder="在此粘贴代码..."
                  class="code-input" data-testid="code" />
        <el-button type="primary" :loading="submitting" style="margin-top:12px" @click="submit">
          提交
        </el-button>
      </template>

      <template v-if="lastResult">
        <h3>最近一次提交结果</h3>
        <el-alert :type="resultType" :closable="false" show-icon>
          <template #title>
            {{ lastResult.status_label }} ｜ 得分 {{ lastResult.score }}
            ｜ 耗时 {{ lastResult.time_ms }}ms ｜ 内存 {{ (lastResult.memory_kb / 1024).toFixed(1) }}MB
          </template>
        </el-alert>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import markdownit from 'markdown-it'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const route = useRoute()
const userStore = useUserStore()
const md = markdownit({ html: false, linkify: true })

const problem = ref<any>(null)
const loading = ref(true)
const language = ref('python3.12')
const code = ref('')
const submitting = ref(false)
const lastResult = ref<any>(null)

const renderedDescription = computed(() =>
  problem.value ? md.render(problem.value.description ?? '') : '')
const resultType = computed(() => {
  const s = lastResult.value?.status
  return s === 'ac' ? 'success' : s === 'ce' ? 'info' : 'error'
})

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

onMounted(async () => {
  try {
    problem.value = await api.get(`/problems/${route.params.id}`)
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
.limits { color: var(--el-text-color-secondary); font-size: 13px; }
.desc { margin-bottom: 24px; }
.code-input :deep(textarea) { font-family: Consolas, Monaco, monospace; }
</style>
