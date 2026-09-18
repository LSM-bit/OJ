<!--
  ProblemManageView.vue - 出题中心（创作视角）
  与刷题列表（ProblemsView，只看公开题）分开：
  这里展示「我管理的题目」——自己的 + 团队的，含未公开草稿；
  可创建题目（三步向导）、继续编辑、发布/撤回、归档/恢复
-->
<template>
  <div class="page">
    <div class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Problems</span>
        <h2>出题中心</h2>
      </div>
      <div class="head-actions">
        <el-button type="primary" size="small" @click="$router.push('/problems/new')">
          创建题目
        </el-button>
      </div>
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="我的题目" name="problems">
        <!-- 归档切换：默认看未归档；切到「已归档」只看归档题（可恢复） -->
        <div class="filter-row">
          <el-radio-group v-model="archived" size="small" @change="reloadFirstPage">
            <el-radio-button :value="false">未归档</el-radio-button>
            <el-radio-button :value="true">已归档</el-radio-button>
          </el-radio-group>
        </div>
        <el-table :data="problems" stripe class="fill-table" v-loading="loading">
          <el-table-column prop="display_id" label="题号" width="80" />
          <el-table-column prop="title" label="标题" min-width="220">
            <template #default="{ row }">
              <router-link :to="`/problems/${row.id}/edit`" class="title-link">
                {{ row.title }}
              </router-link>
            </template>
          </el-table-column>
          <el-table-column prop="difficulty" label="难度" width="90">
            <template #default="{ row }">
              <el-tag :type="diffTag(row.difficulty)" size="small">
                {{ diffLabel(row.difficulty) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.is_public ? 'success' : 'warning'" size="small" effect="light">
                {{ row.is_public ? '已公开' : '草稿' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220">
            <template #default="{ row }">
              <el-button size="small" text type="primary"
                         @click="$router.push(`/problems/${row.id}/edit`)">编辑</el-button>
              <el-button size="small" text @click="$router.push(`/problems/${row.id}`)">预览</el-button>
              <!-- 未归档：可归档；已归档：可恢复 -->
              <el-button v-if="!archived" size="small" text type="warning"
                         @click="setArchive(row, true)">归档</el-button>
              <el-button v-else size="small" text type="success"
                         @click="setArchive(row, false)">恢复</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && problems.length === 0"
                  :description="archived ? '没有已归档的题目' : '还没有题目，点右上角「创建题目」开始出题'" />
        <!-- 分页：full=1 拿 {total, items}，超过一页才显示 -->
        <el-pagination v-if="total > pageSize" class="pager" layout="total, prev, pager, next, jumper"
                       :total="total" :page-size="pageSize" :current-page="page"
                       @current-change="(p: number) => { page = p; load() }" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
// 出题中心：mine=1 拉取我管理的题目（含草稿）；archived 切换归档/未归档视图
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../api/client'

const problems = ref<any[]>([])
const loading = ref(false)
const tab = ref('problems')
const archived = ref(false)

// 分页（full=1 → {total, items}）；切归档视图回到第 1 页
const page = ref(1)
const pageSize = 50
const total = ref(0)

const DIFF = ['', '入门', '简单', '中等', '较难', '困难']
const diffLabel = (d: number) => DIFF[d] ?? '未知'
const diffTag = (d: number) => (['', 'info', 'success', 'warning', 'danger', 'danger'][d] ?? 'info') as any

async function load() {
  loading.value = true
  try {
    const r = await api.get('/problems', {
      params: { mine: 1, archived: archived.value ? 1 : 0, full: 1, page: page.value, size: pageSize },
    }) as any
    problems.value = r.items ?? []
    total.value = r.total ?? 0
  } finally {
    loading.value = false
  }
}

// 归档/未归档切换：重置页码再加载
function reloadFirstPage() {
  page.value = 1
  load()
}

// 归档/恢复（归档不删除，详情仍可访问，可随时恢复）
async function setArchive(row: any, value: boolean) {
  if (value) {
    await ElMessageBox.confirm(
      `归档「${row.title}」后将从题目列表中隐藏，且不能再提交；详情页仍可访问，可随时恢复。`,
      '归档题目', { confirmButtonText: '归档', cancelButtonText: '取消' })
  }
  try {
    await api.put(`/problems/${row.id}/archive`, { archived: value })
    ElMessage.success(value ? '已归档' : '已恢复')
    await load()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}

onMounted(load)
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
  margin-bottom: 8px;
}
.head-actions { display: flex; gap: 8px; }
.filter-row { margin-bottom: 12px; }
.fill-table { width: 100%; }
.title-link { color: var(--el-color-primary); text-decoration: none; }
.title-link:hover { text-decoration: underline; }
.pager {
  margin-top: 12px;
  justify-content: flex-end;
}
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

/* 题面/竞赛的左右分栏 */
.pane-head {
  padding: var(--oj-s3) var(--oj-s4);
  border-bottom: 1px solid var(--oj-line);
}
.pane-body { padding: var(--oj-s4) var(--oj-s5); }
.limits {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-sm);
  color: var(--oj-ink-3);
}
.sample-block {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
  overflow: hidden;
  transition: border-color var(--oj-dur-2) var(--oj-ease);
}
.sample-block:hover { border-color: var(--oj-line-strong); }
.samples-title,
.sample-label {
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--oj-ink-4);
}
.sample-pre { font-family: var(--oj-font-mono); }
</style>
