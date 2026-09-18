<!--
  AiAssistant.vue - AI 助手全局悬浮球 + 抽屉（docs/AI助手Agent设计.md §9）
  右下角悬浮球点开 400x600 抽屉：气泡分侧（用户右/助手左+头像）、工具步骤折叠卡片、
  流式光标、空态快捷引导、贴底智能滚动（上滑出现「回到底部」浮标）；
  消息渲染复用 utils/markdown（代码块自带复制）；比赛禁用态（store.contestBlocked）
  输入框置灰显示「比赛中禁用 AI 助手」。
  状态与 SSE 消费逻辑全在 stores/assistant.ts，本组件只管展示。
-->
<template>
  <!-- 悬浮球（登录后可见；可拖拽，位置记忆，未拖动时点击开合） -->
  <div v-if="userStore.isLoggedIn" class="ai-fab"
       :class="{ 'is-open': store.open, dragging: headDragging }"
       :style="fabStyle" role="button" tabindex="0"
       :title="store.open ? '收起 AI 助手（可拖动整体移动）' : 'AI 编程助教（可拖动）'"
       :aria-expanded="store.open" aria-label="AI 编程助教"
       @pointerdown="onFabDown" @pointermove="onFabMove"
       @pointerup="onFabUp" @pointercancel="onFabUp"
       @keydown.enter.prevent="store.toggle()" @keydown.space.prevent="store.toggle()">
    <el-icon :size="26"><MagicStick /></el-icon>
  </div>

  <!-- 抽屉 -->
  <transition name="ai-drawer">
    <div v-if="store.open" class="ai-drawer"
         :class="{ expanded, dragging: headDragging }" :style="drawerStyle">
      <div class="ai-head" title="按住拖动，与悬浮球一起移动"
           @pointerdown="onHeadDown" @pointermove="onHeadMove"
           @pointerup="onHeadUp" @pointercancel="onHeadUp">
        <span class="ai-brand">
          <span class="ai-brand-mark"><el-icon :size="13"><MagicStick /></el-icon></span>
          <span class="ai-brand-text">
            <span class="ai-title">AI 助教</span>
            <span class="ai-ctx" v-if="contextLabel">{{ contextLabel }}</span>
          </span>
        </span>
        <div class="ai-actions">
          <el-tooltip content="新对话" placement="bottom">
            <el-button text size="small" :icon="Plus" :disabled="!store.messages.length"
                       @click="startNewConversation" />
          </el-tooltip>
          <el-tooltip :content="showList ? '返回对话' : '历史会话'" placement="bottom">
            <el-button text size="small" :icon="Tickets" :class="{ 'is-on': showList }"
                       @click="toggleList" />
          </el-tooltip>
          <el-tooltip :content="expanded ? '收起窗口' : '放大窗口'" placement="bottom">
            <el-button text size="small" :icon="expanded ? Fold : Expand"
                       @click="toggleExpand" />
          </el-tooltip>
          <el-tooltip content="收起（Esc）" placement="bottom">
            <el-button text size="small" :icon="Close" @click="store.toggle()" />
          </el-tooltip>
        </div>
      </div>

      <!-- 会话列表面板（覆盖式）：标题 + 搜索 + 客户端分页 -->
      <div v-if="showList" class="ai-list">
        <div class="ai-list-head">
          <span>历史会话</span>
          <span v-if="convTotal" class="ai-list-count oj-num">{{ convTotal }}</span>
          <el-tooltip content="退出历史（Esc）" placement="bottom">
            <el-button text size="small" :icon="Close" class="ai-list-close"
                       aria-label="退出历史会话" @click="closeList" />
          </el-tooltip>
        </div>
        <el-input v-model="convQuery" size="small" clearable class="ai-list-search"
                  :prefix-icon="Search" placeholder="搜索会话标题" />
        <div class="ai-list-body">
          <div v-if="!filteredConversations.length" class="ai-list-empty">
            {{ convQuery ? '没有匹配的会话' : '暂无历史会话' }}
          </div>
          <div v-for="c in pagedConversations" :key="c.id" class="ai-list-item"
               :class="{ active: c.id === store.currentId }" @click="pickConversation(c.id)">
            <span class="ai-list-title">{{ c.title || '新对话' }}</span>
            <span class="ai-list-time">{{ shortTime(c.updated_at) }}</span>
            <el-icon class="ai-list-del" title="删除会话"
                     @click.stop="store.removeConversation(c.id)"><Delete /></el-icon>
          </div>
        </div>
        <div v-if="convTotal > convPageSize" class="ai-list-pager">
          <el-pagination small background layout="prev, pager, next"
                         :total="convTotal" :page-size="convPageSize"
                         v-model:current-page="convPage" />
        </div>
      </div>

      <!-- 消息区 -->
      <div class="ai-body-wrap">
        <div ref="bodyRef" class="ai-body" @scroll="onScroll">
        <!-- 空态引导：能力介绍 + 快捷提问卡（按当前上下文显隐） -->
        <div v-if="!store.messages.length && !showList" class="ai-empty">
          <div class="ai-empty-hero">
            <el-icon :size="28" class="ai-empty-icon"><MagicStick /></el-icon>
            <p>你好！我是本站的 AI 编程助教 🤖</p>
            <p class="ai-tip">思路引导、错误诊断、题目搜索都可以问我。<br />
               按防作弊要求：<b>不代写完整题解</b>，比赛进行中禁用。</p>
          </div>
          <div class="ai-quick-grid">
            <button v-for="q in quickQuestions" :key="q.text" class="ai-quick"
                    :disabled="banInput" @click="store.send(q.text)">
              <el-icon :size="15"><component :is="q.icon" /></el-icon>
              <span>{{ q.text }}</span>
            </button>
          </div>
        </div>

        <div v-for="(m, i) in store.messages" :key="i" class="ai-msg" :class="m.role">
          <!-- 头像：助手=魔法棒渐变底；用户=昵称首字 -->
          <div class="ai-avatar" :class="m.role">
            <el-icon v-if="m.role === 'assistant'" :size="14"><MagicStick /></el-icon>
            <template v-else>{{ userChar }}</template>
          </div>
          <div class="ai-col">
            <!-- 工具步骤折叠卡 -->
            <div v-if="m.tools.length" class="ai-tools" :class="{ single: m.tools.length === 1 && m.tools[0].done }">
              <div v-if="m.tools.length === 1 && m.tools[0].done" class="ai-tool-row">
                <el-icon class="ai-tool-state ok"><CircleCheck /></el-icon>
                <span class="ai-tool-name">{{ m.tools[0].label }}</span>
                <span v-if="m.tools[0].isError" class="ai-tool-state fail">未成功</span>
              </div>
              <template v-else>
                <div class="ai-tool-head" @click="toggleTools(i)">
                  <el-icon :size="13"><Tools /></el-icon>
                  <span>查看 {{ m.tools.length }} 步操作</span>
                  <el-icon class="ai-tool-caret" :class="{ open: isOpen(i) }"><ArrowDown /></el-icon>
                </div>
                <div v-show="isOpen(i)" class="ai-tool-list">
                  <div v-for="t in m.tools" :key="t.id" class="ai-tool-row">
                    <el-icon v-if="!t.done" class="ai-tool-state is-loading"><Loading /></el-icon>
                    <el-icon v-else-if="!t.isError" class="ai-tool-state ok"><CircleCheck /></el-icon>
                    <el-icon v-else class="ai-tool-state fail"><CircleClose /></el-icon>
                    <span class="ai-tool-name">{{ t.label }}</span>
                    <span class="ai-tool-arg" v-if="argBrief(t)">{{ argBrief(t) }}</span>
                  </div>
                </div>
              </template>
            </div>

            <div class="ai-bubble" :class="{ quiet: !m.text && !m.tools.length && !m.error && !m.streaming }">
              <div v-if="m.text" class="markdown ai-md" v-html="render(m.text)"></div>
              <!-- 流式光标 / 空流式气泡的三点动画 -->
              <span v-if="m.streaming && m.text" class="ai-caret"></span>
              <span v-if="m.streaming && !m.text && !m.error" class="ai-dots"><i></i><i></i><i></i></span>
              <div v-if="m.error" class="ai-error">{{ m.error }}</div>
            </div>
            <div v-if="m.at" class="ai-time">{{ m.at }}</div>
          </div>
        </div>
        </div>

        <!-- 回到底部浮标（用户上滑且底部有新内容时出现） -->
        <transition name="ai-fade">
          <button v-if="showBackBottom && store.messages.length" class="ai-back"
                  @click="backToBottom">
            <el-icon :size="14"><ArrowDown /></el-icon>
            <span>{{ store.sending ? '有新回复 ↓' : '回到底部' }}</span>
          </button>
        </transition>
      </div>

      <!-- 输入区 -->
      <div class="ai-foot">
        <el-alert v-if="store.contestBlocked.active" type="error" :closable="false" class="ai-ban"
                  :title="`比赛中禁用 AI 助手${store.contestBlocked.title ? `（${store.contestBlocked.title}）` : ''}`" />
        <div v-else class="ai-input-row">
          <el-input v-model="store.input" type="textarea" :autosize="{ minRows: 1, maxRows: 5 }"
                    resize="none"
                    :disabled="banInput" placeholder="输入问题…"
                    @keydown.enter.exact.prevent="store.send()" />
          <div class="ai-btns">
            <span class="ai-input-hint">
              <template v-if="store.sending">正在回答…</template>
              <template v-else-if="banInput">当前不可发送</template>
              <template v-else>Enter 发送 · Shift + Enter 换行</template>
            </span>
            <el-button v-if="store.sending" size="small" @click="store.stop()">停止</el-button>
            <el-button v-else type="primary" size="small" :disabled="banInput || !store.input.trim()"
                       @click="store.send()">发送</el-button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import {
  ArrowDown, CircleCheck, CircleClose, Close, Delete, Expand, Fold, Loading,
  MagicStick, Plus, Search, Tickets, Tools, Warning,
} from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { useAssistantStore, type ToolTrace } from '../stores/assistant'
import { useUserStore } from '../stores/user'

const store = useAssistantStore()
const userStore = useUserStore()
const showList = ref(false)
const bodyRef = ref<HTMLElement | null>(null)

const banInput = computed(() => store.contestBlocked.active || store.quotaBlocked)
const userChar = computed(() => (userStore.user?.username ?? '?')[0].toUpperCase())

const contextLabel = computed(() => {
  const c = store.context
  if (c.type === 'problem' && c.display_id) return `#${c.display_id}`
  if (c.type === 'problem_review' && c.display_id) return `审校 #${c.display_id}`
  if (c.type === 'submission' && c.submission_id) return '提交诊断'
  return ''
})

/** 空态快捷提问卡：通用两条 + 按上下文追加 */
const quickQuestions = computed(() => {
  const list = [
    { text: '推荐几道适合入门的题目', icon: Search },
    { text: '我的刷题弱项在哪？', icon: Warning },
  ]
  const c = store.context
  if (c.type === 'problem') list.push({ text: '解释这道题的题面', icon: MagicStick })
  if (c.type === 'problem_review') list.push({ text: '帮我审校这道题', icon: MagicStick })
  if (c.type === 'submission') list.push({ text: '诊断这次提交', icon: Tools })
  return list
})

function render(text: string) {
  return md.render(text)
}

// ---------- 工具折叠卡 ----------
// 展开策略：有未完成步骤时自动展开（等待可感知），完成后可手动折叠/展开
const toolsOpen = reactive<Record<number, boolean>>({})
function isOpen(i: number) {
  const m = store.messages[i]
  if (!m) return false
  if (m.tools.some((t) => !t.done)) return true  // 进行中强制展开
  return toolsOpen[i] ?? false                    // 完成后默认折叠
}
function toggleTools(i: number) { toolsOpen[i] = !isOpen(i) }
// 切换/新建会话时清空展开态（按消息下标记录，跨会话会串台）
watch(() => store.currentId, () => { for (const k of Object.keys(toolsOpen)) delete toolsOpen[Number(k)] })

/** 入参摘要：首个键值对截 30 字 */
function argBrief(t: ToolTrace): string {
  const a = t.args
  if (!a) return ''
  const k = Object.keys(a)[0]
  if (!k) return ''
  const s = `${k}=${typeof a[k] === 'object' ? JSON.stringify(a[k]) : a[k]}`
  return s.length > 30 ? s.slice(0, 30) + '…' : s
}

// ---------- 智能滚动：贴底才跟随流式；上滑出现浮标 ----------
const stickBottom = ref(true)
const pendingBelow = ref(false)  // 贴底判定外，流式中出现了新内容在下方
function onScroll() {
  const el = bodyRef.value
  if (!el) return
  stickBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 40
  if (stickBottom.value) pendingBelow.value = false
}
const showBackBottom = computed(() => !stickBottom.value)
async function scrollBottom(smooth = false) {
  await nextTick()
  const el = bodyRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  stickBottom.value = true
  pendingBelow.value = false
}
async function backToBottom() { await scrollBottom(true) }

// 消息数变化（新气泡）→ 一律滚底；流式增量 → 仅贴底时跟随
watch(() => store.messages.length, () => { stickBottom.value = true; scrollBottom() })
watch(() => store.messages[store.messages.length - 1]?.text?.length, (len, prev) => {
  if (prev != null && len && len > prev) {
    if (stickBottom.value) scrollBottom()
    else pendingBelow.value = true
  }
})
watch(() => store.open, (v) => {
  if (v) { fitDrawerToFab(); scrollBottom() }   // 展开前先给抽屉腾出位置
})

async function pickConversation(id: string) {
  showList.value = false
  await store.openConversation(id)
  await scrollBottom()
}
// ---------- 悬浮球拖拽（Pointer Events + 位置记忆） ----------
const FAB_KEY = 'oj_ai_fab_pos'
const FAB_SIZE = 52
const FAB_PAD = 8
const FAB_MARGIN = 28

/** 把球夹在视口内（换显示器 / 缩窗口后不丢球） */
function clampFab(pos: { x: number; y: number }) {
  const maxX = Math.max(FAB_PAD, window.innerWidth - FAB_SIZE - FAB_PAD)
  const maxY = Math.max(FAB_PAD, window.innerHeight - FAB_SIZE - FAB_PAD)
  return {
    x: Math.min(Math.max(FAB_PAD, pos.x), maxX),
    y: Math.min(Math.max(FAB_PAD, pos.y), maxY),
  }
}
function loadFabPos() {
  const fallback = { x: window.innerWidth - FAB_MARGIN - FAB_SIZE, y: window.innerHeight - FAB_MARGIN - FAB_SIZE }
  try {
    const raw = localStorage.getItem(FAB_KEY)
    if (!raw) return clampFab(fallback)
    const parsed = JSON.parse(raw)
    if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') return clampFab(parsed)
  } catch { /* 脏数据按默认位置处理 */ }
  return clampFab(fallback)
}

const fabPos = ref(loadFabPos())
const viewportW = ref(window.innerWidth)
const viewportH = ref(window.innerHeight)
const fabStyle = computed(() => ({ left: `${fabPos.value.x}px`, top: `${fabPos.value.y}px` }))
/** 抽屉始终从球的正下方居中展开（几何见 drawerBox） */

// ---------- 抽屉：尺寸模式 / 会话列表（搜索 + 客户端分页） ----------
const EXPAND_KEY = 'oj_ai_drawer_expanded'
const expanded = ref(localStorage.getItem(EXPAND_KEY) === '1')
function toggleExpand() {
  expanded.value = !expanded.value
  localStorage.setItem(EXPAND_KEY, expanded.value ? '1' : '0')
  if (store.open) fitDrawerToFab()      // 尺寸变了，重新保证球与抽屉都放得下
}

// ---------- 抽屉与悬浮球一体：从球的正下方居中展开 ----------
const DRAWER_PAD = 12
const DRAWER_GAP = 10
const drawerW = () =>
  Math.min(expanded.value ? 620 : 400, Math.max(200, viewportW.value - DRAWER_PAD * 2))
const drawerH = () =>
  Math.min(expanded.value ? Math.min(760, Math.round(viewportH.value * 0.78)) : 600,
           Math.max(240, viewportH.value - DRAWER_PAD * 2))

/** 抽屉几何：水平中心对齐球，顶边落在球下方 GAP 处，整体夹在视口内 */
const drawerBox = computed(() => {
  const vw = viewportW.value
  const vh = viewportH.value
  const w = drawerW()
  const h = drawerH()
  const rawLeft = fabPos.value.x + FAB_SIZE / 2 - w / 2
  const rawTop = fabPos.value.y + FAB_SIZE + DRAWER_GAP
  return {
    w,
    h,
    left: Math.min(Math.max(DRAWER_PAD, rawLeft), Math.max(DRAWER_PAD, vw - w - DRAWER_PAD)),
    top: Math.min(Math.max(DRAWER_PAD, rawTop), Math.max(DRAWER_PAD, vh - h - DRAWER_PAD)),
  }
})
const drawerStyle = computed(() => ({
  left: `${drawerBox.value.left}px`,
  top: `${drawerBox.value.top}px`,
  width: `${drawerBox.value.w}px`,
  height: `${drawerBox.value.h}px`,
}))

/** 展开前腾位置：球上移到位，使「球 + 抽屉」整体落在视口内，且抽屉水平居中于球 */
function fitDrawerToFab() {
  const w = drawerW()
  const h = drawerH()
  const vw = viewportW.value
  const vh = viewportH.value
  const half = FAB_SIZE / 2
  const y = Math.min(fabPos.value.y, vh - DRAWER_PAD - h - DRAWER_GAP - FAB_SIZE)
  let x = fabPos.value.x
  const minX = Math.max(FAB_PAD, DRAWER_PAD + w / 2 - half)
  const maxX = Math.min(vw - FAB_SIZE - FAB_PAD, vw - DRAWER_PAD - w / 2 - half)
  if (minX <= maxX) x = Math.min(Math.max(x, minX), maxX)
  fabPos.value = clampFab({ x, y })
  localStorage.setItem(FAB_KEY, JSON.stringify(fabPos.value))
}

// ---------- 拖动：球与抽屉始终一体（球居中在抽屉正上方） ----------
const headDragging = ref(false)
let dragState: {
  id: number; sx: number; sy: number
  baseL: number; baseT: number
  baseFabX: number; baseFabY: number
  moved: boolean; tapToggle: boolean
} | null = null

function beginDrag(e: PointerEvent, tapToggle: boolean) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  if ((e.target as HTMLElement).closest('.el-button')) return    // 头部按钮照常点击
  const el = e.currentTarget as HTMLElement
  el.setPointerCapture(e.pointerId)
  dragState = {
    id: e.pointerId, sx: e.clientX, sy: e.clientY,
    baseL: drawerBox.value.left, baseT: drawerBox.value.top,
    baseFabX: fabPos.value.x, baseFabY: fabPos.value.y,
    moved: false, tapToggle,
  }
  headDragging.value = true
}
function moveDrag(e: PointerEvent) {
  if (!dragState || e.pointerId !== dragState.id) return
  const dx = e.clientX - dragState.sx
  const dy = e.clientY - dragState.sy
  if (!dragState.moved && Math.hypot(dx, dy) < 3) return          // 3px 内仍算点击
  dragState.moved = true
  if (!store.open) {                                             // 抽屉未展开：球自由移动
    fabPos.value = clampFab({ x: dragState.baseFabX + dx, y: dragState.baseFabY + dy })
    return
  }
  const { w, h } = drawerBox.value
  const offX = w / 2 - FAB_SIZE / 2                              // 球 left 相对抽屉 left（球水平居中 → 必为正）
  const offY = -(FAB_SIZE + DRAWER_GAP)                          // 球 top 相对抽屉 top（球在上方）
  const vw = viewportW.value
  const vh = viewportH.value
  const minL = Math.max(DRAWER_PAD, FAB_PAD - offX)
  const maxL = Math.max(minL, Math.min(vw - w - DRAWER_PAD, vw - FAB_SIZE - FAB_PAD - offX))
  const minT = Math.max(DRAWER_PAD, FAB_PAD - offY)
  const maxT = Math.max(minT, Math.min(vh - h - DRAWER_PAD, vh - FAB_SIZE - FAB_PAD - offY))
  const left = Math.min(Math.max(minL, dragState.baseL + dx), maxL)
  const top = Math.min(Math.max(minT, dragState.baseT + dy), maxT)
  fabPos.value = { x: Math.round(left + offX), y: Math.round(top + offY) }
}
function endDrag(e: PointerEvent) {
  if (!dragState || e.pointerId !== dragState.id) return
  const { moved, tapToggle } = dragState
  dragState = null
  headDragging.value = false
  if (moved) localStorage.setItem(FAB_KEY, JSON.stringify(fabPos.value))
  else if (tapToggle) store.toggle()                             // 球未拖动 = 点击开合
}
const onFabDown = (e: PointerEvent) => beginDrag(e, true)
const onFabMove = moveDrag
const onFabUp = endDrag
const onHeadDown = (e: PointerEvent) => beginDrag(e, false)
const onHeadMove = moveDrag
const onHeadUp = endDrag

function startNewConversation() {
  showList.value = false
  store.newConversation()
}
function toggleList() {
  showList.value = !showList.value
  if (showList.value) { convPage.value = 1; store.loadConversations() }
}
function closeList() { showList.value = false }

const convQuery = ref('')
const convPage = ref(1)
const convPageSize = 8
const filteredConversations = computed(() => {
  const q = convQuery.value.trim().toLowerCase()
  if (!q) return store.conversations
  return store.conversations.filter((c) => (c.title || '新对话').toLowerCase().includes(q))
})
const convTotal = computed(() => filteredConversations.value.length)
const pagedConversations = computed(() => {
  const start = (convPage.value - 1) * convPageSize
  return filteredConversations.value.slice(start, start + convPageSize)
})
watch(convQuery, () => { convPage.value = 1 })
watch(convTotal, () => {
  if ((convPage.value - 1) * convPageSize >= convTotal.value) convPage.value = 1
})

/** 会话时间的相对表述 */
function shortTime(iso?: string) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 7 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return new Date(t).toLocaleDateString('zh-CN')
}

// ---------- 全局监听：Esc 关抽屉、窗口变化夹球 ----------
function onResize() {
  viewportW.value = window.innerWidth
  viewportH.value = window.innerHeight
  fabPos.value = clampFab(fabPos.value)
  localStorage.setItem(FAB_KEY, JSON.stringify(fabPos.value))
}
function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (showList.value) { showList.value = false; return }
  if (store.open) store.toggle()
}
onMounted(() => {
  window.addEventListener('resize', onResize)
  window.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* 组件内语义变量：全部取 Element 主题色，未来全站 dark 只换 Element 引法即可全绿 */
.ai-drawer {
  --ai-bg: var(--oj-surface);
  --ai-text: var(--oj-ink);
  --ai-sub: var(--oj-ink-3);
  --ai-line: var(--oj-line-soft);
  --ai-fill: var(--oj-surface-2);
  --ai-fill-lighter: var(--oj-surface-2);
  --ai-user-bubble: var(--el-color-primary-light-9);
  --ai-assistant-bubble: var(--oj-surface);
}

/* 悬浮球 */
.ai-fab {
  position: fixed;
  left: 0;
  top: 0;
  will-change: left, top;
  touch-action: none;
  user-select: none;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3));
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  z-index: 2000;
  transition: opacity 0.2s, transform 0.2s;
}
.ai-fab:hover { transform: scale(1.06); }
.ai-fab:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.ai-fab.dragging { transition: none; cursor: grabbing; transform: scale(1.04); }
.ai-fab.hidden { opacity: 0; pointer-events: none; }

/* 抽屉：位置与尺寸由内联 drawerStyle 跟随悬浮球（贴球一侧、底边与球对齐） */
.ai-drawer {
  position: fixed;
  right: auto;
  bottom: auto;
  box-sizing: border-box;   /* 内联尺寸含边框，位置计算才精确 */
  will-change: left, top;
  background: var(--ai-bg);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  z-index: 2001;
  overflow: hidden;
}
/* 放大模式的尺寸由 drawerStyle 计算；拖动中禁用过渡，跟手更紧 */
.ai-drawer.dragging { transition: none; }
.ai-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-bottom: 1px solid var(--ai-line);
  cursor: grab;
  user-select: none;
  touch-action: none;
}
.ai-head:active { cursor: grabbing; }
.ai-head :deep(.el-button) { cursor: pointer; }
.ai-brand { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ai-brand-mark {
  flex: none;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: var(--oj-r2);
  background: var(--oj-accent-soft);
  color: var(--oj-accent-deep);
}
.ai-brand-text { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.ai-title { font-weight: 600; }
.ai-ctx {
  font-size: 12px;
  color: var(--ai-sub);
  background: var(--ai-fill);
  border-radius: var(--oj-r2);
  padding: 1px 6px;
}
.ai-actions { margin-left: auto; display: flex; align-items: center; gap: 2px; }
.ai-actions :deep(.el-button.is-on) {
  color: var(--oj-accent-deep);
  background: var(--oj-accent-soft);
}

/* 会话列表 */
.ai-list {
  position: absolute;
  inset: 0;
  z-index: 4;
  background: var(--ai-bg);
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
}
.ai-list-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
}
.ai-list-count {
  font-size: 11px;
  font-weight: 400;
  color: var(--ai-sub);
  background: var(--ai-fill);
  border-radius: var(--oj-r2);
  padding: 1px 6px;
}
.ai-list-close { margin-left: auto; }
.ai-list-search { flex: none; }
.ai-list-body { flex: 1; min-height: 0; overflow-y: auto; }
.ai-list-time { flex: none; font-size: 11px; color: var(--ai-sub); opacity: 0.75; }
.ai-list-pager { display: flex; justify-content: center; padding-top: 2px; }
.ai-list-pager :deep(.el-pagination) { --el-pagination-font-size: 12px; }
.ai-list-empty { color: var(--ai-sub); font-size: 13px; text-align: center; padding: 24px; }
.ai-list-item {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: var(--oj-r2);
  cursor: pointer;
  font-size: 14px;
}
.ai-list-item:hover { background: var(--ai-fill); }
.ai-list-item.active { background: var(--ai-user-bubble); }
.ai-list-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-list-del { color: var(--ai-sub); }
.ai-list-del:hover { color: var(--el-color-danger); }

/* 消息区 */
.ai-body-wrap { flex: 1; min-height: 0; position: relative; display: flex; }
.ai-body { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 12px 6px; }

/* 空态引导 */
.ai-empty { color: var(--ai-sub); font-size: 13px; padding: 18px 4px 0; }
.ai-empty-hero { text-align: center; }
.ai-empty-icon { color: var(--el-color-primary); }
.ai-empty-hero p { margin: 6px 0 0; }
.ai-tip { line-height: 1.7; font-size: 12px; }
.ai-quick-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 14px;
  padding: 0 8px;
}
.ai-quick {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 9px 10px;
  font-size: 12px;
  color: var(--ai-text);
  background: var(--ai-bg);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, color 0.15s;
}
.ai-quick:hover:not(:disabled) { border-color: var(--el-color-primary); color: var(--el-color-primary); }
.ai-quick:disabled { opacity: 0.5; cursor: not-allowed; }
.ai-quick .el-icon { color: var(--el-color-primary); flex: none; }

/* 气泡行：flex 分侧 */
.ai-msg { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px; }
.ai-msg.user { flex-direction: row-reverse; }
.ai-col { min-width: 0; max-width: 88%; display: flex; flex-direction: column; gap: 4px; }
.ai-msg.user .ai-col { align-items: flex-end; }
.ai-msg.assistant .ai-col { align-items: stretch; flex: 1; }

.ai-avatar {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: var(--oj-r3);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  user-select: none;
}
.ai-avatar.assistant { background: linear-gradient(135deg, var(--el-color-primary), var(--el-color-primary-light-3)); }
.ai-avatar.user { background: var(--el-color-info-light-3); }

.ai-bubble {
  padding: 8px 11px;
  border-radius: var(--oj-r3);
  background: var(--ai-assistant-bubble);
  border: 1px solid var(--ai-line);
  word-break: break-word;
}
.ai-msg.user .ai-bubble {
  background: var(--ai-user-bubble);
  border-color: transparent;
}
.ai-msg.user .ai-bubble :deep(p) { margin: 0; }
.ai-bubble.quiet { display: none; }

.ai-time { font-size: 11px; color: var(--ai-sub); opacity: 0.75; padding: 0 2px; }

/* 工具步骤折叠卡 */
.ai-tools {
  border: 1px solid var(--ai-line);
  border-radius: var(--oj-r3);
  background: var(--ai-fill-lighter);
  overflow: hidden;
}
.ai-tools.single { border: none; background: transparent; }
.ai-tool-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 9px;
  font-size: 12px;
  color: var(--ai-sub);
  cursor: pointer;
  user-select: none;
}
.ai-tool-head:hover { color: var(--el-color-primary); }
.ai-tool-caret { margin-left: auto; transition: transform 0.15s; }
.ai-tool-caret.open { transform: rotate(180deg); }
.ai-tool-list { border-top: 1px dashed var(--ai-line); padding: 4px 9px 6px; }
.ai-tool-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ai-sub);
  padding: 3px 0;
}
.ai-tools.single .ai-tool-row { padding: 0; }
.ai-tool-state.ok { color: var(--el-color-success); }
.ai-tool-state.fail { color: var(--el-color-danger); }
.ai-tool-arg {
  margin-left: auto;
  max-width: 45%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 11px;
  opacity: 0.8;
}

/* 错误与流式光标 */
.ai-error { color: var(--el-color-danger); font-size: 12px; margin-top: 4px; }
.ai-caret {
  display: inline-block;
  width: 7px;
  height: 14px;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--el-color-primary);
  border-radius: 1px;
  animation: ai-blink 1s steps(1) infinite;
}
@keyframes ai-blink { 50% { opacity: 0; } }
.ai-dots { display: inline-flex; gap: 4px; align-items: center; padding: 4px 2px; }
.ai-dots i {
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--ai-sub); opacity: 0.35;
  animation: ai-dot 1.2s ease-in-out infinite;
}
.ai-dots i:nth-child(2) { animation-delay: 0.2s; }
.ai-dots i:nth-child(3) { animation-delay: 0.4s; }
@keyframes ai-dot {
  0%, 60%, 100% { opacity: 0.35; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}

/* Markdown 内容 */
.ai-md { font-size: 14px; line-height: 1.65; }
.ai-md :deep(p:first-child) { margin-top: 0; }
.ai-md :deep(p:last-child) { margin-bottom: 0; }
.ai-md :deep(.code-block) { margin: 8px 0; border-radius: var(--oj-r3); overflow: hidden; }
/* 代码块固定 GitHub 深色系：不依赖主题变量，天然规避全站无 dark 的问题 */
.ai-md :deep(.code-block pre) {
  background: #0d1117;
  color: #e6edf3;
  padding: 9px 10px;
  margin: 0;
  border-radius: 0;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.55;
}
.ai-md :deep(.code-block code) { background: transparent; color: inherit; }
.ai-md :deep(.code-copy-btn) { background: rgba(255, 255, 255, 0.1); color: #e6edf3; }
.ai-md :deep(:not(pre) > code) {
  background: var(--ai-fill);
  border-radius: var(--oj-r2);
  padding: 1px 5px;
  font-size: 12.5px;
}
.ai-md :deep(table) { font-size: 12.5px; }

/* 回到底部浮标（相对消息区容器定位，盖在滚动内容之上） */
.ai-back {
  position: absolute;
  right: 16px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  font-size: 12px;
  color: var(--el-color-primary);
  background: var(--ai-bg);
  border: 1px solid var(--el-color-primary-light-5);
  border-radius: 16px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
  cursor: pointer;
  z-index: 3;
}
.ai-back:hover { background: var(--ai-user-bubble); }
.ai-fade-enter-active, .ai-fade-leave-active { transition: opacity 0.15s, transform 0.15s; }
.ai-fade-enter-from, .ai-fade-leave-to { opacity: 0; transform: translateY(6px); }

/* 输入区 */
.ai-foot { border-top: 1px solid var(--ai-line); padding: 8px; }
.ai-ban { margin-bottom: 0; }
.ai-input-row { display: flex; flex-direction: column; gap: 6px; }
.ai-btns { display: flex; justify-content: flex-end; align-items: center; gap: 8px; }
.ai-stream-hint { font-size: 12px; color: var(--ai-sub); }
.ai-input-hint { margin-right: auto; font-size: 11px; color: var(--ai-sub); }
.ai-input-row :deep(.el-textarea__inner) { border-radius: var(--oj-r3); }

/* 进出场动画 */
.ai-drawer-enter-active, .ai-drawer-leave-active { transition: opacity 0.18s, transform 0.18s; }
.ai-drawer-enter-from, .ai-drawer-leave-to { opacity: 0; transform: translateY(12px); }
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

/* ===== AI 助手：对话框 UI 精修（自球正下方展开的气泡式面板） ===== */
.ai-drawer {
  border-radius: 12px;
  box-shadow: 0 18px 48px -20px oklch(26% 0.022 264 / 0.42);
}
/* 顶部一条朱砂压线，呼应全站顶栏 */
.ai-drawer::before {
  content: '';
  display: block;
  flex: none;
  height: 2px;
  background: linear-gradient(90deg, var(--oj-accent),
              color-mix(in oklab, var(--oj-accent) 20%, transparent));
}
.ai-head {
  padding: 10px 12px;
  border-bottom: 1px solid var(--oj-line);
  background: var(--oj-surface-2);
}
.ai-brand-mark {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--oj-accent), var(--oj-accent-deep));
  color: #fff;
}
.ai-actions :deep(.el-button) { border-radius: var(--oj-r2); }
.ai-actions :deep(.el-button:hover) { background: var(--oj-surface-3); }
.ai-fab.is-open { box-shadow: 0 6px 18px -6px oklch(26% 0.022 264 / 0.5); }
/* 展开腾位/尺寸变化时平滑过渡；拖动期间由 .dragging 关闭过渡，保证跟手 */
.ai-fab {
  transition: left 0.18s var(--oj-ease), top 0.18s var(--oj-ease),
              opacity 0.2s, transform 0.2s;
}

/* 消息区 */
.ai-body { padding: 16px 14px 8px; }
.ai-msg { gap: var(--oj-s3); margin-bottom: var(--oj-s5); }
.ai-avatar { border: 1px solid var(--oj-line); border-radius: 50%; }
.ai-msg.assistant .ai-bubble {
  background: var(--oj-surface);
  border: 1px solid var(--oj-line);
  border-radius: 10px 10px 10px var(--oj-r1);
}
.ai-msg.user .ai-bubble {
  border: 1px solid transparent;
  border-radius: 10px 10px var(--oj-r1) 10px;
  box-shadow: var(--oj-shadow-1);
}
/* 细滚动条 */
.ai-body::-webkit-scrollbar, .ai-list-body::-webkit-scrollbar { width: 8px; }
.ai-body::-webkit-scrollbar-track, .ai-list-body::-webkit-scrollbar-track { background: transparent; }
.ai-body::-webkit-scrollbar-thumb, .ai-list-body::-webkit-scrollbar-thumb {
  background: var(--oj-line-strong);
  border: 2px solid transparent;
  background-clip: content-box;
  border-radius: 8px;
}
.ai-body::-webkit-scrollbar-thumb:hover, .ai-list-body::-webkit-scrollbar-thumb:hover {
  background: var(--oj-ink-4);
  background-clip: content-box;
}

/* 空态与快捷入口 */
.ai-empty-hero { padding: 6px 0 0; }
.ai-empty-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 54px;
  height: 54px;
  border-radius: 50%;
  background: var(--oj-accent-soft);
  color: var(--oj-accent-deep);
}
.ai-quick-grid { gap: 10px; margin-top: 16px; }
.ai-quick {
  padding: 10px 12px;
  border: 1px solid var(--oj-line);
  border-radius: 8px;
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.ai-quick:hover:not(:disabled) {
  border-color: var(--oj-accent);
  box-shadow: var(--oj-shadow-1);
  transform: translateY(-1px);
}

/* 工具步骤卡 */
.ai-tools { border-radius: 8px; }
.ai-tool-head { padding: 7px 10px; }
.ai-tool-row {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r2);
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.ai-tool-row:hover { background: var(--oj-surface-2); }
.ai-tools.single .ai-tool-row { border: none; }

/* 历史会话面板 */
.ai-list { padding: 12px; gap: 8px; }
.ai-list-head { padding-bottom: 2px; }
.ai-list-item {
  border-radius: var(--oj-r2);
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.ai-list-item.active { box-shadow: inset 2px 0 0 var(--oj-accent); }

/* 输入区 */
.ai-foot {
  padding: 10px 12px 12px;
  border-top: 1px solid var(--oj-line);
  background: var(--oj-surface-2);
}
.ai-input-row :deep(.el-textarea__inner) { border-radius: 8px; background: var(--oj-surface); }

/* 交接动画：从球的正下方展开 */
.ai-drawer-enter-active, .ai-drawer-leave-active {
  transition: opacity 0.18s var(--oj-ease), transform 0.18s var(--oj-ease);
  transform-origin: top center;
}
.ai-drawer-enter-from, .ai-drawer-leave-to { opacity: 0; transform: translateY(-8px) scale(0.98); }
</style>
