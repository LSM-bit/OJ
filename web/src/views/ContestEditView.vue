<!--
  ContestEditView.vue - 创建比赛第一步：基本信息
  权限模型：所有登录用户都可创建比赛（后端强校验），支持归属个人或团队
  表单：标题/简介/赛制/时间/封榜/归属/可见性；题目挑选在第二步独立页
  （ContestProblemPickView），表单数据存 sessionStorage(contest_new_draft) 传递
-->
<template>
  <div class="page">
    <div class="page-head">
      <h2>创建比赛</h2>
      <el-button size="small" @click="$router.push('/contests')">返回比赛列表</el-button>
    </div>

    <!-- 步骤条 -->
    <el-steps :active="1" align-center class="steps">
      <el-step title="基本信息" />
      <el-step title="选择题目" />
    </el-steps>

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
          <span class="pick-hint">下一步选择比赛题目（支持标签筛选、题号/标题搜索），也可以之后再配置</span>
        </div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="goPick">下一步：选择题目</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
// 第一步：填写基本信息 → 存草稿到 sessionStorage → 跳 /contests/new/pick 选题创建
// 回到本页时自动恢复草稿（从第二步点「上一步」返回不丢已填内容）
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()

const DRAFT_KEY = 'contest_new_draft'
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

// 团队列表（仅可管理的）
const myTeams = ref<any[]>([])
const manageableTeams = computed(() =>
  myTeams.value.filter((t) => ['owner', 'admin'].includes(t.my_role)))

// 校验基本信息后存草稿，进入第二步选题页
function goPick() {
  if (!form.value.title.trim()) return ElMessage.warning('请填写比赛标题')
  if (!form.value.start_at || !form.value.end_at) return ElMessage.warning('请选择开始/结束时间')
  if (new Date(form.value.end_at) <= new Date(form.value.start_at))
    return ElMessage.warning('结束时间必须晚于开始时间')
  if (form.value.owner_type === 'team' && !form.value.team_id)
    return ElMessage.warning('请选择归属团队')
  sessionStorage.setItem(DRAFT_KEY, JSON.stringify(form.value))
  router.push('/contests/new/pick')
}

onMounted(async () => {
  if (!userStore.isLoggedIn) {
    ElMessage.warning('请先登录')
    router.push('/login')
    return
  }
  // 恢复草稿（仅当存在时；新建流程首次进入为空不动）
  const raw = sessionStorage.getItem(DRAFT_KEY)
  if (raw) {
    try { Object.assign(form.value, JSON.parse(raw)) } catch { /* ignore */ }
  }
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
.steps { max-width: 420px; margin-bottom: 18px; }
.form { max-width: 720px; }
.unit { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 13px; }
.problems-pick { width: 100%; }
.pick-hint { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 6px; }
</style>
