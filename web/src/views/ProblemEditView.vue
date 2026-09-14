<!--
  ProblemEditView.vue - 题目创建/编辑页（三步向导）
  第 1 步 题面：基本信息 + Markdown 描述（带预览）
  第 2 步 样例和用例：上传 zip 数据包 / 手工逐条添加用例，预览输入输出
  第 3 步 测试：提交标程跑全部用例逐个比对，全部通过后才能发布公开
  创建（第 1 步保存）后才进入第 2/3 步；权限后端强校验
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>{{ isEdit ? `编辑题目 ${detail?.display_id ? '#' + detail.display_id : ''}` : '创建题目' }}</h2>
      <div>
        <el-button v-if="isEdit" size="small" @click="$router.push(`/problems/${pid}`)">查看题目</el-button>
      </div>
    </div>

    <!-- 步骤条 -->
    <el-steps :active="step" align-center class="steps" finish-status="success">
      <el-step title="题面" description="标题、难度、描述" />
      <el-step title="样例和用例" description="上传测试数据" />
      <el-step title="测试" description="标程验证后发布" />
    </el-steps>

    <!-- ===================== 第 1 步：题面 ===================== -->
    <div v-show="step === 0" class="step-body">
      <div class="form-grid">
        <!-- 左：表单 -->
        <div class="form-col">
          <el-form label-width="90px" label-position="left">
            <el-form-item label="标题">
              <el-input v-model="form.title" maxlength="128" placeholder="题目名称" />
            </el-form-item>
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" style="width:140px">
                <el-option v-for="(d, i) in DIFF.slice(1)" :key="i" :label="d" :value="i" />
              </el-select>
            </el-form-item>
            <el-form-item label="标签">
              <div class="tags-field">
                <el-tag v-for="t in tags" :key="t" size="small" closable class="picked-tag"
                        @close="tags = tags.filter((x) => x !== t)">
                  {{ t }}
                </el-tag>
                <el-button size="small" @click="tagPickerRef?.open()">
                  <el-icon style="margin-right:4px"><Plus /></el-icon>选择标签
                </el-button>
              </div>
            </el-form-item>
            <el-form-item label="时限">
              <el-input-number v-model="form.time_limit_ms" :min="100" :max="30000" :step="100" />
              <span class="unit">ms</span>
            </el-form-item>
            <el-form-item label="内存">
              <el-input-number v-model="form.memory_limit_mb" :min="16" :max="2048" :step="16" />
              <span class="unit">MB</span>
            </el-form-item>
            <el-form-item v-if="!isEdit" label="归属">
              <el-select v-model="form.owner_type" style="width:140px">
                <el-option label="我的账号" value="user" />
                <el-option label="团队" value="team" />
              </el-select>
              <el-select v-if="form.owner_type === 'team'" v-model="form.team_id"
                         placeholder="选择团队" style="width:170px; margin-left:8px">
                <el-option v-for="t in manageableTeams" :key="t.id" :label="t.name" :value="t.id" />
              </el-select>
            </el-form-item>
          </el-form>
        </div>

        <!-- 右：题面编辑 + 预览 -->
        <div class="desc-col">
          <div class="desc-tabs">
            <el-radio-group v-model="descTab" size="small">
              <el-radio-button value="edit">编辑题面</el-radio-button>
              <el-radio-button value="preview">预览</el-radio-button>
            </el-radio-group>
          </div>
          <el-input v-if="descTab === 'edit'" v-model="form.description" type="textarea"
                    :autosize="false" class="desc-editor" resize="none"
                    placeholder="支持 Markdown 与 LaTeX 公式" />
          <div v-else class="desc-preview markdown" v-html="rendered"></div>
        </div>
      </div>
    </div>

    <!-- ===================== 第 2 步：样例和用例 ===================== -->
    <div v-show="step === 1" class="step-body">
      <div class="cases-toolbar">
        <el-button type="primary" size="small" @click="openAddCase(true)">添加样例</el-button>
        <el-button size="small" @click="openAddCase(false)">添加隐藏用例</el-button>
        <el-button size="small" @click="showData = true">上传 zip 数据包</el-button>
        <span class="cases-meta">
          样例 {{ casesInfo.samples?.length ?? 0 }} 个 ｜ 隐藏用例 {{ casesInfo.cases?.length ?? 0 }} 个
          <template v-if="casesInfo.has_data">（数据版本 {{ casesInfo.data_version }}）</template>
        </span>
      </div>

      <el-alert type="info" :closable="false" style="margin-bottom:12px"
                title="样例会展示在题面中供用户参考；隐藏用例仅用于判题，用户不可见" />

      <!-- 样例（题面可见） -->
      <h4 v-if="casesInfo.samples?.length" class="case-sec-title">
        样例（题面可见，{{ casesInfo.samples.length }} 个）
      </h4>
      <el-table v-if="casesInfo.samples?.length" :data="casesInfo.samples" size="small" class="cases-table">
        <el-table-column prop="idx" label="#" width="60" />
        <el-table-column prop="case_id" label="用例 ID" width="100" />
        <el-table-column label="输入预览" min-width="200">
          <template #default="{ row }">
            <pre class="io-preview">{{ row.input_preview || '（空）' }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="期望输出预览" min-width="200">
          <template #default="{ row }">
            <pre class="io-preview">{{ row.output_preview || '（空）' }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="removeCase(row.idx)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 隐藏用例 -->
      <h4 v-if="casesInfo.cases?.length" class="case-sec-title">
        隐藏用例（仅判题使用，{{ casesInfo.cases.length }} 个）
      </h4>
      <el-table v-if="casesInfo.cases?.length" :data="casesInfo.cases" size="small" class="cases-table">
        <el-table-column prop="idx" label="#" width="60" />
        <el-table-column prop="case_id" label="用例 ID" width="100" />
        <el-table-column label="输入预览" min-width="200">
          <template #default="{ row }">
            <pre class="io-preview">{{ row.input_preview || '（空）' }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="期望输出预览" min-width="200">
          <template #default="{ row }">
            <pre class="io-preview">{{ row.output_preview || '（空）' }}</pre>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button size="small" text type="danger" @click="removeCase(row.idx)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!casesInfo.has_data"
                description="请添加样例/隐藏用例，或上传 zip 数据包（manifest.json + cases/*.in|*.out）" />
    </div>

    <!-- ===================== 第 3 步：测试 ===================== -->
    <div v-show="step === 2" class="step-body">
      <div class="split">
        <!-- 左：题面预览（与做题页一致） -->
        <div class="pane pane-left">
          <div class="pane-head">
            <span class="pane-title">
              {{ detail?.display_id ? `#${detail.display_id}. ` : '' }}{{ form.title || '未命名题目' }}
              <el-tag :type="diffTag(form.difficulty)" size="small" style="margin-left:8px">
                {{ diffLabel(form.difficulty) }}
              </el-tag>
            </span>
          </div>
          <div class="pane-body">
            <p class="limits">时间限制 {{ form.time_limit_ms }}ms ｜ 内存限制 {{ form.memory_limit_mb }}MB</p>
            <div class="markdown" v-html="rendered"></div>

            <!-- 样例（与做题页展示一致） -->
            <template v-if="casesInfo.samples?.length">
              <h4 class="samples-title">样例</h4>
              <div v-for="(s, i) in casesInfo.samples" :key="i" class="sample-block">
                <div class="sample-label">输入 #{{ Number(i) + 1 }}</div>
                <pre class="sample-pre">{{ s.input_preview || '（空）' }}</pre>
                <div class="sample-label">输出 #{{ Number(i) + 1 }}</div>
                <pre class="sample-pre">{{ s.output_preview || '（空）' }}</pre>
              </div>
            </template>
          </div>
        </div>

        <!-- 右：标程编辑器（引用统一编辑器工作台，验题页自定义头/尾） -->
        <div class="pane pane-right">
          <CodeWorkbench v-model:code="solution.code" v-model:language="solution.language"
                         :problem-id="pid || undefined" :show-submit="false" :show-reset="false">
            <template #head-after-lang>
              <el-tag v-if="casesInfo.verified_at" type="success" size="small" effect="light">
                已通过验证 {{ casesInfo.verified_at.slice(0, 16).replace('T', ' ') }}
              </el-tag>
            </template>
            <template #head-right>
              <el-button type="primary" size="small" :loading="verifying"
                         :disabled="!casesInfo.has_data || !solution.code.trim()" @click="verify">
                运行测试（{{ (casesInfo.samples?.length ?? 0) + (casesInfo.cases?.length ?? 0) }} 个用例）
              </el-button>
            </template>
            <template #footer>
              <!-- 验证结果 -->
              <div v-if="verifyResult" class="verify-result">
                <el-alert :type="verifyResult.ok ? 'success' : 'error'" :closable="false"
                          :title="verifyResult.ok
                            ? `全部通过（${verifyResult.passed}/${verifyResult.total}）`
                            : `未全部通过（${verifyResult.passed}/${verifyResult.total}）`"
                          style="margin-bottom:10px" />
                <el-table :data="verifyResult.cases" size="small" border class="verify-table">
                  <el-table-column prop="idx" label="#" width="48" />
                  <el-table-column prop="case_id" label="用例" width="88" />
                  <el-table-column label="结果" width="96">
                    <template #default="{ row }">
                      <el-tag size="small" :type="row.passed ? 'success' : 'danger'">
                        {{ row.passed ? '通过' : row.status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="time_used_ms" label="耗时(ms)" width="88" />
                  <el-table-column prop="memory_used_kb" label="内存(KB)" width="88" />
                  <el-table-column label="期望输出" min-width="120">
                    <template #default="{ row }">
                      <pre class="io-preview">{{ row.expected_preview || '（空）' }}</pre>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </template>
          </CodeWorkbench>
        </div>
      </div>
    </div>

    <!-- 底部导航 -->
    <div class="foot-bar">
      <el-button @click="$router.back()">取消</el-button>
      <el-button v-if="step > 0" @click="step--">上一步</el-button>
      <el-button v-if="step === 0" type="primary" :loading="saving" @click="saveStep1">
        {{ isEdit ? '保存并继续' : '创建并继续' }}
      </el-button>
      <el-button v-if="step === 1" type="primary" :disabled="!casesInfo.has_data" @click="goStep3">
        下一步：测试
      </el-button>
      <!-- 第 3 步：测试通过才能发布；未通过只能存草稿 -->
      <template v-if="step === 2">
        <el-button :loading="publishing" @click="publish(false)">保存为草稿</el-button>
        <el-button type="success" :loading="publishing" :disabled="!casesInfo.verified_at"
                   @click="publish(true)">
          {{ form.is_public ? '已公开，重新保存' : '保存并发布' }}
        </el-button>
      </template>
    </div>

    <!-- zip 数据包上传 -->
    <el-dialog v-model="showData" title="上传测试数据 zip 包" width="480">
      <p class="data-hint">
        zip 包结构：manifest.json + cases/*.in + cases/*.out，上传后整体替换并作废已有验证
      </p>
      <input type="file" accept=".zip" @change="onFileChange" />
      <el-input v-model="dataVersion" placeholder="数据版本，如 v1" style="margin-top:10px" />
      <template #footer>
        <el-button @click="showData = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!dataFile" @click="uploadData">
          上传
        </el-button>
      </template>
    </el-dialog>

    <!-- 手工添加用例（区分样例/隐藏） -->
    <el-dialog v-model="showAddCase" :title="newCase.is_sample ? '添加样例（题面可见）' : '添加隐藏用例'" width="560">
      <div class="add-case-grid">
        <div>
          <div class="add-case-label">输入（stdin）</div>
          <el-input v-model="newCase.input" type="textarea" :rows="6" placeholder="样例输入" />
        </div>
        <div>
          <div class="add-case-label">期望输出</div>
          <el-input v-model="newCase.output" type="textarea" :rows="6" placeholder="样例输出" />
        </div>
      </div>
      <template #footer>
        <el-button @click="showAddCase = false">取消</el-button>
        <el-button type="primary" :loading="addingCase" @click="addCase">添加</el-button>
      </template>
    </el-dialog>

    <!-- 标签选择弹窗：搜索选择已有标签实例 / 搜不到时创建（v-model 绑定已选标签名数组） -->
    <TagPicker ref="tagPickerRef" v-model="tags" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import md from '../utils/markdown'
import { api } from '../api/client'
import { Plus } from '@element-plus/icons-vue'
import CodeWorkbench from '../components/CodeWorkbench.vue'
import TagPicker from '../components/TagPicker.vue'

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

const route = useRoute()
const router = useRouter()
// 雪花 ID 超出 JS 安全整数范围，保持字符串透传（Number() 会丢精度）
const pid = computed(() => (route.params.id as string) ?? '')
const isEdit = computed(() => !!route.params.id)

// 三步向导：0 题面 / 1 样例用例 / 2 测试
const step = ref(isEdit.value ? 0 : 0)
const detail = ref<any>(null)

const form = ref({
  title: '', description: '', difficulty: 1,
  time_limit_ms: 2000, memory_limit_mb: 256,
  is_public: false, owner_type: 'user', team_id: null as number | null,
})
// 标签：弹窗从 tags 表实例中选择/新建（不再手填逗号分隔文本）
const tags = ref<string[]>([])
const tagPickerRef = ref<InstanceType<typeof TagPicker> | null>(null)
const descTab = ref('edit')
const saving = ref(false)
const myTeams = ref<any[]>([])
const manageableTeams = computed(() =>
  myTeams.value.filter((t) => ['owner', 'admin'].includes(t.my_role)))

const rendered = computed(() => md.render(form.value.description ?? ''))

// 第 2 步：用例信息（samples=题面可见样例；cases=隐藏用例）
const casesInfo = ref<any>({ samples: [], cases: [], has_data: false, data_version: 'v1', verified_at: null })
const showData = ref(false)
const dataFile = ref<File | null>(null)
const dataVersion = ref('v1')
const uploading = ref(false)
const showAddCase = ref(false)
const addingCase = ref(false)
const newCase = ref({ input: '', output: '', is_sample: true })

// 第 3 步：标程验证
const solution = ref({ language: 'python3.12', code: '' })
const verifying = ref(false)
const verifyResult = ref<any>(null)
const publishing = ref(false)

function onFileChange(e: Event) {
  dataFile.value = (e.target as HTMLInputElement).files?.[0] ?? null
}

async function loadCases() {
  if (!isEdit.value) return
  try {
    casesInfo.value = await api.get(`/problems/${pid.value}/cases`) as any
    if (casesInfo.value.solution_code) {
      solution.value.code = casesInfo.value.solution_code
      solution.value.language = casesInfo.value.solution_language ?? 'python3.12'
    }
  } catch { /* 无权限时静默 */ }
}

onMounted(async () => {
  try {
    myTeams.value = await api.get('/teams') as any
  } catch { /* 未登录忽略 */ }
  if (isEdit.value) {
    try {
      detail.value = await api.get(`/problems/${pid.value}`) as any
      const p = detail.value
      form.value.title = p.title
      form.value.description = p.description
      form.value.difficulty = p.difficulty
      form.value.time_limit_ms = p.time_limit_ms
      form.value.memory_limit_mb = p.memory_limit_mb
      form.value.is_public = p.is_public
      tags.value = p.tags ?? []
      await loadCases()
    } catch {
      ElMessage.error('题目不存在或无权查看')
      router.push('/problems')
    }
  }
})

// 第 1 步保存：创建或更新题面，成功后进入第 2 步
async function saveStep1() {
  if (!form.value.title.trim()) {
    ElMessage.warning('请填写标题')
    return
  }
  saving.value = true
  try {
    if (isEdit.value) {
      await api.put(`/problems/${pid.value}`, { ...form.value, tags: tags.value })
      ElMessage.success('题面已保存')
    } else {
      if (form.value.owner_type === 'team' && !form.value.team_id) {
        ElMessage.warning('请选择团队')
        return
      }
      const p = await api.post('/problems', { ...form.value, tags: tags.value }) as any
      ElMessage.success('创建成功，继续上传测试数据')
      router.replace(`/problems/${p.id}/edit`)
      step.value = 1
      return
    }
    step.value = 1
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

function goStep3() {
  verifyResult.value = null
  step.value = 2
}

async function uploadData() {
  if (!dataFile.value) return
  uploading.value = true
  const fd = new FormData()
  fd.append('file', dataFile.value)
  fd.append('data_version', dataVersion.value)
  try {
    const r = await api.post(`/problems/${pid.value}/data`, fd) as any
    ElMessage.success(`上传成功：${r.cases} 个测试点`)
    showData.value = false
    await loadCases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '上传失败')
  } finally {
    uploading.value = false
  }
}

function openAddCase(isSample: boolean) {
  newCase.value = { input: '', output: '', is_sample: isSample }
  showAddCase.value = true
}

async function addCase() {
  if (!newCase.value.input && !newCase.value.output) {
    ElMessage.warning('输入/输出不能同时为空')
    return
  }
  addingCase.value = true
  try {
    await api.post(`/problems/${pid.value}/cases/sample`, newCase.value)
    ElMessage.success(newCase.value.is_sample ? '样例已添加' : '隐藏用例已添加')
    showAddCase.value = false
    newCase.value = { input: '', output: '', is_sample: true }
    await loadCases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '添加失败')
  } finally {
    addingCase.value = false
  }
}

async function removeCase(idx: number) {
  try {
    await api.delete(`/problems/${pid.value}/cases/${idx}`)
    await loadCases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '删除失败')
  }
}

// 第 3 步：标程验证
async function verify() {
  verifying.value = true
  verifyResult.value = null
  try {
    verifyResult.value = await api.post(`/problems/${pid.value}/verify`, solution.value) as any
    await loadCases()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '验证失败')
  } finally {
    verifying.value = false
  }
}

// 发布（is_public=true，需验证凭证）或存草稿（is_public=false）
async function publish(isPublic: boolean) {
  publishing.value = true
  try {
    await api.put(`/problems/${pid.value}/publish`, { is_public: isPublic })
    form.value.is_public = isPublic
    ElMessage.success(isPublic ? '已发布为公开题目' : '已保存为草稿')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  } finally {
    publishing.value = false
  }
}
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.steps { margin-bottom: 18px; }
/* step-body 内部滚动：内容（用例表等）超高时在自己的区域里滚，
   不会溢出盒子遮挡下方 foot-bar 保存按钮 */
.step-body { flex: 1; min-height: 0; overflow-y: auto; }

.form-grid {
  display: flex;
  gap: 16px;
  height: 100%;
  min-height: 420px;
}
.form-col { flex: 1; min-width: 320px; }
/* 标签字段：已选标签 + 选择按钮 */
.tags-field {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.picked-tag { margin-right: 2px; }
.desc-col {
  flex: 1.2;
  min-width: 380px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}
.desc-tabs {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.desc-editor { flex: 1; height: 100%; }
.desc-editor :deep(.el-textarea__inner) {
  height: 100%;
  border-radius: 0;
  border: none;
  box-shadow: none;
}
.desc-preview {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}
.unit { margin-left: 8px; color: var(--el-text-color-secondary); }

/* 第 2 步 */
.cases-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.cases-meta { font-size: 13px; color: var(--el-text-color-secondary); }
.cases-meta.warn { color: var(--el-color-warning); }
.cases-table { width: 100%; }
.io-preview {
  margin: 0;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 6px 8px;
}

/* 第 3 步：左题面 / 右编辑器，与做题页一致的分栏布局 */
.split {
  display: flex;
  gap: 12px;
  height: 100%;
  min-height: 520px;
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
.pane-right { flex: 1; min-width: 420px; }
.pane-head {
  flex-shrink: 0;
  padding: 10px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  font-weight: 600;
  white-space: nowrap;
}
.pane-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}
.limits { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 0; }
.samples-title { margin: 18px 0 8px; }
.sample-block { margin-bottom: 12px; }
.sample-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 6px 0 4px;
}
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
/* 验证结果：固定高度面板，内部滚动 */
.verify-result {
  flex-shrink: 0;
  border-top: 1px solid var(--el-border-color-lighter);
  padding: 10px 12px;
  max-height: 260px;
  overflow-y: auto;
}
.verify-table { width: 100%; }
.io-preview {
  margin: 0;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 80px;
  overflow-y: auto;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 6px 8px;
}

.foot-bar {
  flex-shrink: 0;
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.case-sec-title { margin: 6px 0 8px; }
.data-hint { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 0; }
.add-case-grid { display: flex; gap: 12px; }
.add-case-grid > div { flex: 1; }
.add-case-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
</style>
