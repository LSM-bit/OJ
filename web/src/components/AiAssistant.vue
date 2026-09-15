<!--
  AiAssistant.vue - AI 助手全局悬浮球 + 抽屉（docs/AI助手Agent设计.md §9）
  右下角悬浮球点开 400x600 抽屉：气泡分侧（用户右/助手左+头像）、工具步骤折叠卡片、
  流式光标、空态快捷引导、贴底智能滚动（上滑出现「回到底部」浮标）；
  消息渲染复用 utils/markdown（代码块自带复制）；比赛禁用态（store.contestBlocked）
  输入框置灰显示「比赛中禁用 AI 助手」。
  状态与 SSE 消费逻辑全在 stores/assistant.ts，本组件只管展示。
-->
<template>
  <!-- 悬浮球（登录后可见） -->
  <div v-if="userStore.isLoggedIn" class="ai-fab" :class="{ hidden: store.open }"
       title="AI 编程助教" @click="store.toggle()">
    <el-icon :size="26"><MagicStick /></el-icon>
  </div>

  <!-- 抽屉 -->
  <transition name="ai-drawer">
    <div v-if="store.open" class="ai-drawer">
      <div class="ai-head">
        <span class="ai-title">AI 助教</span>
        <span class="ai-ctx" v-if="contextLabel">{{ contextLabel }}</span>
        <div class="ai-actions">
          <el-tooltip content="新对话">
            <el-button text size="small" :icon="Plus" @click="store.newConversation()" />
          </el-tooltip>
          <el-tooltip content="历史会话">
            <el-button text size="small" :icon="Tickets"
                       @click="showList = !showList; showList && store.loadConversations()" />
          </el-tooltip>
          <el-button text size="small" :icon="Close" @click="store.toggle()" />
        </div>
      </div>

      <!-- 会话列表面板（覆盖式） -->
      <div v-if="showList" class="ai-list">
        <div v-if="!store.conversations.length" class="ai-list-empty">暂无历史会话</div>
        <div v-for="c in store.conversations" :key="c.id" class="ai-list-item"
             :class="{ active: c.id === store.currentId }" @click="pickConversation(c.id)">
          <span class="ai-list-title">{{ c.title || '新对话' }}</span>
          <el-icon class="ai-list-del" @click.stop="store.removeConversation(c.id)"><Delete /></el-icon>
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
          <el-input v-model="store.input" type="textarea" :autosize="{ minRows: 1, maxRows: 4 }"
                    resize="none"
                    :disabled="banInput" :placeholder="banInput ? '输入已禁用' : '输入问题，Enter 发送 / Shift+Enter 换行'"
                    @keydown.enter.exact.prevent="store.send()" />
          <div class="ai-btns">
            <span v-if="store.sending" class="ai-stream-hint">正在回答…</span>
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
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  ArrowDown, CircleCheck, CircleClose, Close, Delete, Loading, MagicStick,
  Plus, Search, Tickets, Tools, Warning,
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
watch(() => store.open, (v) => { if (v) scrollBottom() })

async function pickConversation(id: string) {
  showList.value = false
  await store.openConversation(id)
  await scrollBottom()
}
</script>

<style scoped>
/* 组件内语义变量：全部取 Element 主题色，未来全站 dark 只换 Element 引法即可全绿 */
.ai-drawer {
  --ai-bg: var(--el-bg-color);
  --ai-text: var(--el-text-color-primary);
  --ai-sub: var(--el-text-color-secondary);
  --ai-line: var(--el-border-color-lighter);
  --ai-fill: var(--el-fill-color-light);
  --ai-fill-lighter: var(--el-fill-color-lighter);
  --ai-user-bubble: var(--el-color-primary-light-9);
  --ai-assistant-bubble: var(--el-bg-color);
}

/* 悬浮球 */
.ai-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
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
.ai-fab.hidden { opacity: 0; pointer-events: none; }

/* 抽屉 */
.ai-drawer {
  position: fixed;
  right: 20px;
  bottom: 20px;
  width: 400px;
  height: min(600px, calc(100vh - 90px));
  background: var(--ai-bg);
  border: 1px solid var(--el-border-color-light);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  z-index: 2001;
  overflow: hidden;
}
.ai-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 10px;
  border-bottom: 1px solid var(--ai-line);
}
.ai-title { font-weight: 600; }
.ai-ctx {
  font-size: 12px;
  color: var(--ai-sub);
  background: var(--ai-fill);
  border-radius: 4px;
  padding: 1px 6px;
}
.ai-actions { margin-left: auto; display: flex; align-items: center; }

/* 会话列表 */
.ai-list {
  position: absolute;
  inset: 39px 0 0 0;
  background: var(--ai-bg);
  z-index: 2;
  overflow-y: auto;
  padding: 6px;
}
.ai-list-empty { color: var(--ai-sub); font-size: 13px; text-align: center; padding: 24px; }
.ai-list-item {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
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
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
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
  border-radius: 8px;
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
  border-radius: 10px;
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
  border-radius: 8px;
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
.ai-md :deep(.code-block) { margin: 8px 0; border-radius: 8px; overflow: hidden; }
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
  border-radius: 4px;
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
.ai-input-row :deep(.el-textarea__inner) { border-radius: 8px; }

/* 进出场动画 */
.ai-drawer-enter-active, .ai-drawer-leave-active { transition: opacity 0.18s, transform 0.18s; }
.ai-drawer-enter-from, .ai-drawer-leave-to { opacity: 0; transform: translateY(12px); }
</style>
