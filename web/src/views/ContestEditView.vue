<!--
  ContestEditView.vue - 创建比赛页
  权限模型：所有登录用户都可创建比赛（后端强校验），支持归属个人或团队
  表单：标题/简介/赛制/时间/封榜 + 从自己可见的公有题目中挑选比赛题目（按 A/B/C 顺序）
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>创建比赛</h2>
      <el-button size="small" @click="$router.push('/contests')">返回比赛列表</el-button>
    </div>

    <el-form label-width="110px" label-position="left" class="form">
      <el-form-item label="比赛标题">
        <el-input v-model="form.title" maxlength="128" placeholder="比赛名称" />
      </el-form-item>
      <el-form-item label="赛制">
        <el-radio-group v-model="form.rule">
          <el-radio-button value="acm">ACM 赛制</el-radio-button>
          <el-radio-button value="oi">OI 赛制</el-radio-button>
          <el-radio-button value="ioi">IOI 赛制</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="开始时间">
        <el-date-picker v-model="form.start_at" type="datetime" placeholder="选择开始时间"
                        value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm" />
      </el-form-item>
      <el-form-item label="结束时间">
        <el-date-picker v-model="form.end_at" type="datetime" placeholder="选择结束时间"
                        value-format="YYYY-MM-DDTHH:mm:ss" format="YYYY-MM-DD HH:mm" />
      </el-form-item>
      <el-form-item label="封榜">
        <el-input-number v-model="form.board_freeze_minutes" :min="0" :max="720" :step="10" />
        <span class="unit">分钟（0 = 不封榜）</span>
      </el-form-item>
      <el-form-item label="简介">
        <el-input v-model="form.description" type="textarea" :rows="4"
                  placeholder="比赛说明（可选）" />
      </el-form-item>
      <el-form-item label="归属">
        <el-select v-model="form.owner_type" style="width:140px">
          <el-option label="我的账号" value="user" />
          <el-option label="团队" value="team" />
        </el-select>
        <el-select v-if="form.owner_type === 'team'" v-model="form.team_id"
                   placeholder="选择团队" style="width:170px; margin-left:8px">
          <el-option v-for="t in manageableTeams" :key="t.id" :label="t.name" :value="t.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="可见性">
        <el-radio-group v-model="form.is_public">
          <el-radio-button :value="true">公开</el-radio-button>
          <el-radio-button :value="false">私有</el-radio-button>
        </el-radio-group>
        <span class="unit">{{ visibilityHint }}</span>
      </el-form-item>
      <el-form-item label="比赛题目">
        <div class="problems-pick">
          <el-select v-model="pickProblemId" filterable placeholder="添加题目（我的/团队/公开题目）"
                     style="width: 280px" @change="addProblem">
            <el-option v-for="p in selectableProblems" :key="p.id"
                       :label="`#${p.display_id} ${p.title}`" :value="p.id" />
          </el-select>
          <el-table v-if="pickedProblems.length" :data="pickedProblems" size="small" class="pick-table">
            <el-table-column label="题号" width="70">
              <template #default="{ $index }">{{ String.fromCharCode(65 + $index) }}</template>
            </el-table-column>
            <el-table-column prop="title" label="标题" min-width="200" />
            <el-table-column label="操作" width="80">
              <template #default="{ $index }">
                <el-button size="small" text type="danger" @click="pickedProblems.splice($index, 1)">
                  移除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="pick-hint">暂未添加题目，创建后也可以再配置</div>
        </div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">创建比赛</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const submitting = ref(false)
const form = ref({
  title: '',
  rule: 'acm',
  start_at: '',
  end_at: '',
  board_freeze_minutes: 0,
  description: '',
  owner_type: 'user',
  team_id: null as number | null,
  is_public: true,
})

// 可见性提示：私有比赛仅自己（或团队成员）可见/进入
const visibilityHint = computed(() =>
  form.value.is_public
    ? '所有人可见，可报名参加'
    : form.value.owner_type === 'team'
      ? '仅团队成员可见（团队内部比赛）'
      : '仅自己可见')

// 题目挑选（出题视角：自己的私有题也可入赛；他人私有题后端会拒绝）
const allProblems = ref<any[]>([])
const pickedProblems = ref<any[]>([])
// 雪花 ID 超出 Number 安全范围，统一用字符串保存
const pickProblemId = ref<string>('')
const selectableProblems = computed(() =>
  allProblems.value.filter((p) => !pickedProblems.value.some((x) => x.id === p.id)))

// 团队列表（仅可管理的）
const myTeams = ref<any[]>([])
const manageableTeams = computed(() =>
  myTeams.value.filter((t) => ['owner', 'admin'].includes(t.my_role)))

function addProblem(pid: string) {
  const p = allProblems.value.find((x) => x.id === pid)
  if (p) pickedProblems.value.push(p)
  pickProblemId.value = ''
}

async function submit() {
  if (!form.value.title.trim()) return ElMessage.warning('请填写比赛标题')
  if (!form.value.start_at || !form.value.end_at) return ElMessage.warning('请选择开始/结束时间')
  if (form.value.owner_type === 'team' && !form.value.team_id)
    return ElMessage.warning('请选择归属团队')
  submitting.value = true
  try {
    const body: any = {
      title: form.value.title.trim(),
      description: form.value.description,
      rule: form.value.rule,
      // value-format 含秒的本地时间串；Date 构造按本地时区解析，转真正的 UTC ISO
      start_at: new Date(form.value.start_at).toISOString(),
      end_at: new Date(form.value.end_at).toISOString(),
      board_freeze_minutes: form.value.board_freeze_minutes,
      owner_type: form.value.owner_type,
      is_public: form.value.is_public,
      problem_ids: pickedProblems.value.map((p) => p.id),
    }
    if (form.value.owner_type === 'team') body.team_id = form.value.team_id
    const created: any = await api.post('/contests', body)
    ElMessage.success('比赛已创建')
    router.push(`/contests/${created.id}`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  // mine=1：出题视角，自己的私有题也可选入比赛
  allProblems.value = await api.get('/problems?mine=1') as any
  myTeams.value = await api.get('/teams') as any
})
</script>

<style scoped>
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.page-head h2 { margin: 0; }
.form { max-width: 720px; }
.unit { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 13px; }
.problems-pick { width: 100%; }
.pick-table { margin-top: 10px; }
.pick-hint { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 6px; }
</style>
