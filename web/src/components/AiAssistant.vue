<!--
  AiAssistant.vue - AI 助手全局悬浮球 + 抽屉（docs/AI助手Agent设计.md §9）
  右下角悬浮球点开 400x600 抽屉：会话列表 tab + 当前对话；
  消息渲染复用 utils/markdown；工具过程（tool_start/tool_result）显示灰色小字让等待可感知；
  比赛禁用态（store.contestBlocked）输入框置灰显示「比赛中禁用 AI 助手」。
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
      <div ref="bodyRef" class="ai-body">
        <div v-if="!store.messages.length && !showList" class="ai-welcome">
          <p>你好！我是本站的 AI 编程助教 🤖</p>
          <p class="ai-tip">可以问我思路引导、错误诊断、题目搜索。
             按防作弊要求：<b>不代写完整题解</b>，比赛进行中禁用。</p>
        </div>
        <div v-for="(m, i) in store.messages" :key="i" class="ai-msg" :class="m.role">
          <!-- 工具过程：灰色小字 -->
          <div v-for="t in m.tools" :key="t.id" class="ai-tool">
            <el-icon class="is-loading" v-if="!t.done"><Loading /></el-icon>
            {{ t.label }}<span v-if="t.done && t.isError">（未成功，助手将调整思路）</span>
          </div>
          <div v-if="m.text" class="markdown ai-md" v-html="render(m.text)"></div>
          <div v-if="m.error" class="ai-error">{{ m.error }}</div>
        </div>
        <div v-if="store.sending" class="ai-thinking">正在思考…</div>
      </div>

      <!-- 输入区 -->
      <div class="ai-foot">
        <el-alert v-if="store.contestBlocked.active" type="error" :closable="false" class="ai-ban"
                  :title="`比赛中禁用 AI 助手${store.contestBlocked.title ? `（${store.contestBlocked.title}）` : ''}`" />
        <div v-else class="ai-input-row">
          <el-input v-model="store.input" type="textarea" :rows="2" resize="none"
                    :disabled="banInput" :placeholder="banInput ? '输入已禁用' : '输入问题，Enter 发送 / Shift+Enter 换行'"
                    @keydown.enter.exact.prevent="store.send()" />
          <div class="ai-btns">
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
import { computed, nextTick, ref, watch } from 'vue'
import { Close, Delete, Loading, MagicStick, Plus, Tickets } from '@element-plus/icons-vue'
import md from '../utils/markdown'
import { useAssistantStore } from '../stores/assistant'
import { useUserStore } from '../stores/user'

const store = useAssistantStore()
const userStore = useUserStore()
const showList = ref(false)
const bodyRef = ref<HTMLElement | null>(null)

const banInput = computed(() => store.contestBlocked.active || store.quotaBlocked)

const contextLabel = computed(() => {
  const c = store.context
  if (c.type === 'problem' && c.display_id) return `#${c.display_id}`
  if (c.type === 'submission' && c.submission_id) return '提交诊断'
  return ''
})

function render(text: string) {
  return md.render(text)
}

async function pickConversation(id: string) {
  showList.value = false
  await store.openConversation(id)
}

// 新消息自动滚到底
watch(() => [store.messages.length, store.messages[store.messages.length - 1]?.text],
  async () => {
    await nextTick()
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight
  }, { deep: false })
</script>

<style scoped>
/* 悬浮球 */
.ai-fab {
  position: fixed;
  right: 28px;
  bottom: 28px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--el-color-primary);
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
  background: #fff;
  border: 1px solid var(--el-border-color-light);
  border-radius: 10px;
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
  padding: 8px 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.ai-title { font-weight: 600; }
.ai-ctx {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 1px 6px;
}
.ai-actions { margin-left: auto; display: flex; align-items: center; }

/* 会话列表 */
.ai-list {
  position: absolute;
  inset: 37px 0 0 0;
  background: #fff;
  z-index: 2;
  overflow-y: auto;
  padding: 6px;
}
.ai-list-empty { color: var(--el-text-color-secondary); font-size: 13px; text-align: center; padding: 24px; }
.ai-list-item {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}
.ai-list-item:hover { background: var(--el-fill-color-light); }
.ai-list-item.active { background: var(--el-color-primary-light-9); }
.ai-list-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-list-del { color: var(--el-text-color-secondary); }
.ai-list-del:hover { color: var(--el-color-danger); }

/* 消息区 */
.ai-body { flex: 1; min-height: 0; overflow-y: auto; padding: 12px; }
.ai-welcome { color: var(--el-text-color-secondary); font-size: 13px; padding: 24px 8px; }
.ai-tip { margin-top: 8px; line-height: 1.6; }
.ai-msg { margin-bottom: 12px; }
.ai-msg.user {
  align-self: flex-end;
}
.ai-msg.user :deep(p) { margin: 0; }
.ai-msg.user .ai-md {
  background: var(--el-color-primary-light-9);
  border-radius: 8px;
  padding: 8px 10px;
  float: right;
  max-width: 92%;
  clear: both;
}
.ai-msg.assistant .ai-md { clear: both; }
.ai-tool {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.ai-error {
  color: var(--el-color-danger);
  font-size: 12px;
  margin-top: 4px;
  clear: both;
}
.ai-thinking { color: var(--el-text-color-secondary); font-size: 12px; }
.ai-md { font-size: 14px; word-break: break-word; }
.ai-md :deep(pre) {
  background: var(--el-fill-color-light);
  padding: 8px;
  border-radius: 6px;
  overflow-x: auto;
}
.ai-md :deep(.code-block) { margin: 6px 0; }

/* 输入区 */
.ai-foot { border-top: 1px solid var(--el-border-color-lighter); padding: 8px; }
.ai-ban { margin-bottom: 0; }
.ai-input-row { display: flex; flex-direction: column; gap: 6px; }
.ai-btns { display: flex; justify-content: flex-end; }

/* 进出场动画 */
.ai-drawer-enter-active, .ai-drawer-leave-active { transition: opacity 0.18s, transform 0.18s; }
.ai-drawer-enter-from, .ai-drawer-leave-to { opacity: 0; transform: translateY(12px); }
</style>
