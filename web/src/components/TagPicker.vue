<!--
  TagPicker.vue - 标签选择弹窗（出题表单用）
  弹窗内搜索 /problems/tags/search 选择已有标签实例；
  搜不到时可创建新实例（POST /problems/tags，重名幂等）。
  v-model 绑定已选标签名数组（题目 tags 仍以名字数组存储，弹窗只负责"从实例中选择"）
-->
<template>
  <el-dialog v-model="visible" title="选择标签" width="460" :append-to-body="true">
    <el-input v-model="keyword" placeholder="搜索标签，如：模拟 / 动态规划" clearable
              @input="search">
      <template #prefix>
        <el-icon><Search /></el-icon>
      </template>
    </el-input>

    <!-- 已选 -->
    <div v-if="modelValue.length" class="picked">
      <span class="picked-label">已选：</span>
      <el-tag v-for="t in modelValue" :key="t" size="small" closable
              @close="remove(t)">{{ t }}</el-tag>
    </div>

    <!-- 搜索结果 -->
    <div v-loading="searching" class="result-list">
      <div v-for="t in results" :key="t.id" class="result-item"
           :class="{ picked: modelValue.includes(t.name), disabled: modelValue.includes(t.name) }"
           @click="!modelValue.includes(t.name) && pick(t)">
        <span>{{ t.name }}</span>
        <el-icon v-if="modelValue.includes(t.name)" class="check"><Check /></el-icon>
      </div>
      <el-empty v-if="!searching && results.length === 0" :image-size="60"
                :description="keyword ? `没有「${keyword}」，可创建新标签` : '暂无标签，输入名称创建'" />
    </div>

    <template #footer>
      <el-button v-if="canCreate" type="primary" plain size="small" @click="createTag">
        创建「{{ keyword.trim() }}」
      </el-button>
      <el-button @click="visible = false">完成</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Check, Search } from '@element-plus/icons-vue'
import { api } from '../api/client'

// v-model：已选标签名数组
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string[]): void }>()

const visible = ref(false)
const keyword = ref('')
const searching = ref(false)
const results = ref<{ id: string; name: string }[]>([])

// 关键字非空且不在已选/结果中 → 显示"创建"按钮
const canCreate = computed(() => {
  const name = keyword.value.trim()
  return !!name && name.length <= 32
    && !props.modelValue.includes(name)
    && !results.value.some((t) => t.name === name)
})

async function search() {
  searching.value = true
  try {
    const items = await api.get('/problems/tags/search', { params: { q: keyword.value.trim() } }) as any
    results.value = items ?? []
  } catch {
    results.value = []
  } finally {
    searching.value = false
  }
}

// 每次打开弹窗都重新拉一次全量标签（新标签可能刚被别人创建）
watch(visible, (v) => {
  if (v) {
    keyword.value = ''
    search()
  }
})

function pick(t: { name: string }) {
  emit('update:modelValue', [...props.modelValue, t.name])
}

function remove(t: string) {
  emit('update:modelValue', props.modelValue.filter((x) => x !== t))
}

async function createTag() {
  const name = keyword.value.trim()
  if (!name) return
  try {
    await api.post('/problems/tags', { name })
    emit('update:modelValue', [...props.modelValue, name])
    keyword.value = ''
    await search()
    ElMessage.success(`已创建标签「${name}」`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  }
}

defineExpose({ open: () => (visible.value = true) })
</script>

<style scoped>
.picked {
  margin-top: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.picked-label { font-size: 13px; color: var(--el-text-color-secondary); }
.result-list {
  margin-top: 10px;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  min-height: 120px;
}
.result-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 14px;
  cursor: pointer;
  border-bottom: 1px dashed var(--el-border-color-lighter);
}
.result-item:last-child { border-bottom: none; }
.result-item:hover { background: var(--el-fill-color-light); }
.result-item.picked { color: var(--el-color-primary); }
.result-item.disabled { cursor: default; opacity: 0.75; }
.check { color: var(--el-color-primary); }
</style>
