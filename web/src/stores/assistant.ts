/*
  assistant.ts - AI 助手 Pinia store
  悬浮球/抽屉的共享状态：会话列表、当前对话消息、SSE 流式消费（fetch + ReadableStream 手解，
  EventSource 不支持 POST）、比赛禁用态（403 contest_active → 输入置灰）、配额提示。
  后端契约见 docs/AI助手Agent设计.md §4/§6/§9。
*/
import { defineStore } from 'pinia'
import { api } from '../api/client'

export interface ToolTrace {
  id: string
  name: string
  label: string
  done: boolean
  isError: boolean
  /** 工具入参摘要（tool_start 事件下发；回放时取 blocks 里的 input） */
  args?: Record<string, any>
}

export interface ChatMsg {
  role: 'user' | 'assistant'
  text: string
  tools: ToolTrace[]
  error?: string
  /** 流式输出中（光标动画与「思考中」气泡的判定依据） */
  streaming?: boolean
  /** 展示时间（回放取 created_at，实时取本地时间），hh:mm */
  at?: string
}

export interface ConvItem {
  id: string
  title: string
  context: Record<string, any>
  updated_at: string
}

// 工具名 → 用户可读的过程提示（§9：tool_start/tool_result 渲染成灰色小字）
const TOOL_LABELS: Record<string, string> = {
  get_problem: '正在查看题目…',
  get_submission: '正在查看你的提交…',
  list_case_results: '正在核对测试点结果…',
  run_on_sample: '正在公开样例上试跑…',
  search_problems: '正在搜索相关题目…',
  get_my_stats: '正在查看你的刷题统计…',
  get_hint: '正在整理提示…',
  get_problem_full: '正在通读题目与用例数据…',
  get_problem_stats: '正在核对本作出题数据…',
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('oj_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** 展示时间 hh:mm（回放按本地时区渲染，与 created_at 的 UTC 只差时区偏移，够用） */
function fmtTime(iso?: string | null): string {
  const d = iso ? new Date(iso) : new Date()
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export const useAssistantStore = defineStore('assistant', {
  state: () => ({
    open: false,
    conversations: [] as ConvItem[],
    currentId: null as string | null,
    context: {} as Record<string, any>,
    messages: [] as ChatMsg[],
    sending: false,
    // 比赛禁用态（红线）：{active, title}——进行中比赛参赛者收到 403 后置位
    contestBlocked: { active: false, title: '' },
    quotaBlocked: false,
    input: '',
    abort: null as AbortController | null,
  }),
  actions: {
    toggle() {
      this.open = !this.open
      if (this.open && !this.conversations.length) this.loadConversations()
    },
    /** 页面入口按钮调用：带上下文打开并预填输入 */
    async openWithContext(context: Record<string, any>, prefill: string) {
      this.open = true
      this.context = context
      this.currentId = null
      this.messages = []
      this.contestBlocked = { active: false, title: '' }
      this.input = prefill
      await this.probeContest()
    },
    /** 打开时主动探测比赛禁用态：向 chat 发一次空探测不划算，这里靠首次 403 置位；
        但题目/提交页入口可先查会话可用性（轻量：直接尝试，失败即置灰） */
    async probeContest() {
      // 无独立探测接口——首次 send 收到 403 时置位即可，这里仅复位
      this.contestBlocked = { active: false, title: '' }
    },
    async loadConversations() {
      try {
        this.conversations = (await api.get('/assistant/conversations')) as any
      } catch { /* 未登录等静默 */ }
    },
    async openConversation(id: string) {
      if (this.sending) this.stop()
      this.currentId = id
      const conv = this.conversations.find((c) => c.id === id)
      this.context = conv?.context ?? {}
      try {
        const rows = (await api.get(`/assistant/conversations/${id}/messages`)) as any[]
        this.messages = rows.map((m) => {
          const blocks = m.content ?? []
          const text = blocks.filter((b: any) => b.type === 'text')
            .map((b: any) => b.text).join('')
          // 回放：落库的 assistant 消息必属已结束轮次（tool_result 块不入库，
          // 失败态由 router 在持久化时并入 tool_use.is_error），done 恒真
          const tools: ToolTrace[] = blocks.filter((b: any) => b.type === 'tool_use')
            .map((b: any) => ({
              id: b.id, name: b.name, label: TOOL_LABELS[b.name] ?? `调用 ${b.name}`,
              args: b.input ?? undefined,
              done: true, isError: !!b.is_error,
            }))
          return { role: m.role, text, tools, at: fmtTime(m.created_at) }
        })
      } catch {
        this.messages = []
      }
    },
    newConversation() {
      if (this.sending) this.stop()
      this.currentId = null
      this.messages = []
      this.input = ''
    },
    async removeConversation(id: string) {
      await api.delete(`/assistant/conversations/${id}`)
      this.conversations = this.conversations.filter((c) => c.id !== id)
      if (this.currentId === id) this.newConversation()
    },
    stop() {
      this.abort?.abort()
    },
    /** 发送一条消息并逐事件消费 SSE（text_delta / tool_start / tool_result / done / error） */
    async send(text?: string) {
      const content = (text ?? this.input).trim()
      if (!content || this.sending) return
      this.input = ''
      const wasNew = !this.currentId  // 首轮：后端会异步 LLM 摘要标题，稍后要再刷一次列表
      this.messages.push({ role: 'user', text: content, tools: [], at: fmtTime() })
      const draft: ChatMsg = { role: 'assistant', text: '', tools: [], streaming: true, at: fmtTime() }
      this.messages.push(draft)
      this.sending = true
      const ctrl = new AbortController()
      this.abort = ctrl
      try {
        const base = api.defaults.baseURL ?? ''
        const resp = await fetch(`${base}/assistant/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders() },
          body: JSON.stringify({
            // 雪花 ID 保持字符串回传（Number() 会丢 2^53 以上精度；Pydantic 自动 str→int）
            conversation_id: this.currentId || null,
            message: content,
            context: this.context,
          }),
          signal: ctrl.signal,
        })
        if (!resp.ok) {
          // 先撤占位气泡，再以整行错误消息呈现（403 contest_active / 429 配额 / 503）
          this.messages.splice(this.messages.indexOf(draft), 1)
          await this._handleHttpError(resp)
          return
        }
        await this._consumeSse(resp, draft)
      } catch (e: any) {
        if (e?.name !== 'AbortError') {
          draft.error = '连接中断，请重试'
        }
      } finally {
        draft.streaming = false  // 无论成败/停止/断连，气泡流式光标收尾
        this.sending = false
        this.abort = null
        this.loadConversations()
        // 新会话首轮：后端异步 LLM 标题摘要晚于本流结束，延迟再刷一次列表拿新标题
        if (wasNew) setTimeout(() => this.loadConversations(), 2500)
      }
    },
    async _handleHttpError(resp: Response) {
      let detail: any = null
      try { detail = (await resp.json())?.detail } catch { /* 非 JSON 忽略 */ }
      const reason = typeof detail === 'object' ? detail?.reason : undefined
      if (resp.status === 403 && reason === 'contest_active') {
        // 红线：比赛中完全禁用——置灰输入框并提示
        this.contestBlocked = { active: true, title: detail?.contest_title ?? '' }
        this.messages.push({ role: 'assistant', text: '', tools: [],
          error: `比赛进行中禁用 AI 助手${detail?.contest_title ? `（${detail.contest_title}）` : ''}，赛后可继续使用` })
      } else if (resp.status === 429 || reason === 'daily_quota') {
        this.quotaBlocked = true
        this.messages.push({ role: 'assistant', text: '', tools: [],
          error: detail?.message ?? '今日对话配额已用完' })
      } else if (resp.status === 503) {
        this.messages.push({ role: 'assistant', text: '', tools: [],
          error: typeof detail === 'string' ? detail : 'AI 助手暂不可用' })
      } else if (resp.status === 401) {
        this.messages.push({ role: 'assistant', text: '', tools: [], error: '登录已过期，请重新登录' })
      } else {
        this.messages.push({ role: 'assistant', text: '', tools: [],
          error: typeof detail === 'string' ? detail : `请求失败（${resp.status}）` })
      }
    },
    async _consumeSse(resp: Response, draft: ChatMsg) {
      const reader = resp.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        // SSE 帧以空行分隔；行内 event:/data: 两行成一组
        let sep
        while ((sep = buf.indexOf('\n\n')) >= 0) {
          const frame = buf.slice(0, sep)
          buf = buf.slice(sep + 2)
          let event = 'message'
          let data = ''
          for (const line of frame.split('\n')) {
            if (line.startsWith('event: ')) event = line.slice(7).trim()
            else if (line.startsWith('data: ')) data += (data ? '\n' : '') + line.slice(6)
          }
          if (!data) continue
          this._applyEvent(event, JSON.parse(data), draft)
        }
      }
    },
    _applyEvent(event: string, data: any, draft: ChatMsg) {
      switch (event) {
        case 'text_delta':
          draft.text += data.text ?? ''
          break
        case 'tool_start':
          draft.tools.push({ id: data.id, name: data.name,
            label: TOOL_LABELS[data.name] ?? `调用 ${data.name}`,
            args: data.input ?? undefined, done: false, isError: false })
          break
        case 'tool_result': {
          const t = draft.tools.find((x) => x.id === data.id)
          if (t) { t.done = true; t.isError = !!data.is_error }
          break
        }
        case 'done':
          draft.streaming = false
          if (data.conversation_id != null) this.currentId = String(data.conversation_id)
          if (data.stop_reason === 'max_turns') draft.error = '（本轮工具往返已达上限，请细化问题继续）'
          else if (data.stop_reason === 'timeout') draft.error = '（响应超时，已按当前进度收尾）'
          break
        case 'error':
          draft.streaming = false
          draft.error = data.message ?? '助手出错'
          break
      }
    },
  },
})
