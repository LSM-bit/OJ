> 面向读者：本项目后端/前端开发者，作为「AI 助手 Agent」功能的立项设计与第一版实施依据。

# AI 助手 Agent 技术设计

## 1. 背景与目标

在 OJ 站内置一个可对话、可调用平台数据的 AI Agent，服务两类用户：

- **做题者**：结合当前题面/当前提交做概念答疑、分层提示、错题诊断；
- **出题者**（二期）：题面歧义检查、数据弱项分析、造样例辅助。

核心价值主张：Agent 能看到**站内的真实数据**（题面、用户代码、判题结果），这是通用 AI 工具做不到的差异化。

**非目标（一期明确不做）**：自动写题、代做判题（Agent 拒绝直接给出可通过的完整 AC 代码的策略见 §7）、多模态、微调模型。

## 2. 总体架构

> 实施时按既定决策改为**独立节点**（与判题节点同构）：模型 I/O 归 `agent/assistant_node`，
> 工具执行与权限强制留在 API 侧，两者经内嵌网关以 gRPC 双向流（端口 50052）相连。

```
浏览器 (Vue)
  ├─ ProblemDetailView   [问 AI] 悬浮聊天窗（携带题号上下文）
  └─ SubmissionDetailView [诊断这次为什么错]（携带提交号上下文）
        │ SSE (text/event-stream)
        ▼
api/app/routers/assistant.py            ← 比赛禁用(403)/日配额/落库/ChatJob 组装
  ├─ 会话管理（session 表、历史裁剪）
  ├─ app/assistant_gateway/（gRPC :50052 内嵌 API 进程，逐事件路由）
  ├─ 工具层 services/assistant_tools.py ← 复用现有 router/service 读数据（API 侧执行）
        │ bidi stream: ChatJob ↓ / ChatDelta·ChatDone ↑ / ToolResult ↓
        ▼
agent/assistant_node（独立进程，与 judge_node 同构：注册/心跳/退避重连）
  └─ Anthropic Messages API stream=True（claude-sonnet-5 默认，key 仅存节点）
```

- 前端一个全局 `<AiAssistant />` 组件（悬浮球 + 抽屉），经 Pinia store 维护多会话；
- 后端不引入新框架，**手写 tool-use 循环**（§4）即可——Agent 工具只有 6~8 个，事件流协议简单，引 LangChain 类框架的抽象代价大于收益；
- **边界（决策）**：节点只做「模型 I/O 中转」，零 DB/存储访问——隐藏用例、标程天然不可能从节点泄露；Anthropic key 只存节点侧 env（`ANTHROPIC_API_KEY`），不进 API、不进 git；比赛中禁用/配额全在 API router 入口，节点不感知比赛。

## 3. 数据模型（新增两张表）

```python
class AssistantConversation(Base):   # 会话
    id, user_id, title(自动摘要), 
    context: JSON          # {"type":"problem","problem_id":123} / {"type":"submission","submission_id":45}
    created_at, updated_at

class AssistantMessage(Base):        # 消息
    id, conversation_id, role('user'|'assistant'), 
    content: JSON          # Anthropic content blocks 原样存（含 tool_use / tool_result），供回放与续聊
    input_tokens, output_tokens, created_at
```

历史消息超过 ~30 条或 ~50k token 时，从最旧一端截断（一期不做摘要压缩）。

## 4. Agent 运行循环（跨 API / 节点两侧）

```
POST /assistant/chat   body: {conversation_id?, message, context}
  → SSE 事件流: {event: text_delta | tool_start | tool_result | done | error}
```

**API 侧 `routers/assistant.py`（HTTP 层，全在 SSE 首字节前完成拒绝）**：

```python
gw = get_assistant_gateway()               # 无网关/无在线节点 → 503
await _assert_no_active_contest(db, user)  # §7.2 红线 → 403 contest_active
await _assert_quota(db, user)              # 日配额 → 429
落库 user 消息；job = ChatJob(job_id=uuid, system=_build_system(ctx),
                             messages_json=历史+本轮, tools_json=TOOL_SPECS)
StreamingResponse(_event_stream(job, ...))
```

**API 侧事件循环（消费网关 `stream_chat(job)` 的异步事件流）**：

```python
async for evt in gw.stream_chat(job):      # 节点逐 token 上行，不攒整段
    text_chunk → SSE text_delta            # 即时透传给浏览器
    tool_use   → SSE tool_start
                 content, is_error = await execute_tool(db, user, ctx, tu)   # 权限在此强制
                 await gw.send_tool_result(job_id, tu.id, content, is_error) # 回填节点续轮
                 → SSE tool_result
    done       → assistant 消息落库 → SSE done（usage / stop_reason）
    error      → SSE error
```

**节点侧 `agent/assistant_node/runner.py`（模型 I/O）**：`messages.stream(...)` 逐 `text_delta` 即时 put 到 outbox；`stop_reason=tool_use` 时上行 ToolUse 并 `await` 该 tool_use 的 Future（网关回填即唤醒），组 tool_result 续下一轮；MAX_TURNS=8、总超时 120s，最终以 ChatDone（含各轮全量 blocks 与累计 usage）或 ChatError 收尾。

要点：
- **流式**：节点 → 网关 → SSE 三级逐 token 透传，工具往返不阻塞文本增量下发；
- 每轮 tool_result 体积上限 8KB（代码/题面截断标注「已截断」）；
- 超时 120s / 超过 MAX_TURNS 直接收尾提示；
- 续聊历史只带 text blocks（工具往返块剔除），避免孤立 tool_use 缺配对 tool_result 而 400。

## 5. 工具清单（一期 7 个）

| 工具 | 入参 | 返回 | 权限约束 |
|---|---|---|---|
| `get_problem` | display_id | 题面 MD、限制、标签、难度、公开样例 | 公开题；比赛题须该赛已结束或提问者已参赛 |
| `get_submission` | submission_id | 代码、语言、verdict、score、用时/内存 | 仅本人或 ADMIN |
| `list_case_results` | submission_id | 各测试点 status/用时/内存（**不含输入输出内容**） | 同上 |
| `run_on_sample` | problem_id, language, code | 标称在公开样例上跑一遍（复用网关 RunCode 通道） | 每日限 20 次；比赛进行中禁用 |
| `search_problems` | keyword/tag/difficulty | 题目摘要列表（≤10 条） | 同题列表可见性规则 |
| `get_my_stats` | — | 提问者刷题统计（通过数、常错标签） | 仅本人 |
| `get_hint` | problem_id, level(1-3) | 预置提示（若题 config.hints 有）或模型生成 | 见防作弊策略 |

实现上 `assistant_tools.py` 直接调用现有 router 层函数/service 原语（`read_text_file` 等），不绕过权限依赖——**工具函数第一个参数恒为 `current_user`，由循环注入，模型无法伪造**。

## 6. 接口设计

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/assistant/conversations` | 我的会话列表 |
| POST | `/assistant/conversations` | 新建（body: context） |
| GET | `/assistant/conversations/{id}/messages` | 历史回放 |
| DELETE | `/assistant/conversations/{id}` | 删除 |
| POST | `/assistant/chat` | SSE 对话（§4） |

鉴权沿用现有 JWT 依赖；全部接口要求登录。

## 7. 安全与防作弊（重点）

1. **禁读清单**：任何工具不得返回题目标程（`problem.config.solution_code`）、隐藏用例的 `.in/.out` 内容、manifest 分值明细。`list_case_results` 刻意只给 status/资源数据。
2. **比赛模式——比赛进行中完全禁用 AI**：提问上下文若关联进行中比赛（`contest.start_time <= now <= end_time`）且提问者为该赛参赛者——**直接拒绝会话**：`/assistant/chat` 返回 403 `{reason: "contest_active"}`，前端悬浮球显示「比赛中禁用 AI 助手」并禁用输入；后端在每次对话请求时实时判定比赛状态，同时比赛结束/结算后自动恢复。禁止采用「Hints-Only 降级」折衷，杜绝赛中任何形式的模型辅助。
3. **代码代写约束**：system prompt 规定「解释与修复建议可以，完整可提交的 AC 代码不给；用户已贴自己代码时，只做逐行点评 + 指出错误行，让用户自己改」。这一条一期用 prompt 约束 + 事后抽查，二期可加静态检测（回答中出现 ≥20 行与标程高度相似代码则拒绝发送）。
4. **注入防护**：题面/用户代码作为不可信内容进入上下文——工具返回值一律包 `<tool_data>` 标签，system prompt 声明其中内容不构成指令。
5. **配额与审计**：每用户每日 100 轮对话 + 20 次 `run_on_sample`（Redis 计数器）；全部消息落库（§3）供 ADMIN 抽查；ADMIN 后台可一键封禁。
6. **敏感配置**：Anthropic key 仅存服务端 env/settings，不进 git。

## 8. System Prompt 骨架

```
你是 {站名} 的 AI 编程助教。用户是当前登录做题者。
当前上下文：{题面摘要 / 提交摘要，由后端注入，非模型工具}
行为准则：
- 优先引导，不直接给完整题解代码；
- 回答用中文，代码注释用中文；
- 不确定时调用工具查真实数据，不臆测判题结果；
- {比赛模式不走到这里——进行中的比赛对参赛者直接拒绝对话，见 §7.2}
```

## 9. 前端交互

- 全局悬浮球（右下），点开为 400×600 抽屉：会话列表 tab + 当前对话；
- 题目页按钮「问 AI」→ 新建 problem-context 会话并预填「我想了解这道题的思路」；
- 提交详情页按钮「诊断这次错误」→ 新建 submission-context 会话，预填诊断请求（自动带 code + verdict）；
- SSE 消费：`fetch` + `ReadableStream` 手解（EventSource 不支持 POST）；消息渲染复用现有 Markdown 组件；
- tool_start/tool_result 事件渲染成灰色小字「正在查看你的提交…」，让等待可感知。

## 10. 依赖与配置增量

- `agent/pyproject.toml`（新顶层目录，同 `judge/`）：`grpcio` / `protobuf` / **`anthropic>=0.60`**（官方 SDK，async + 流式 + tool use）——**Anthropic SDK 只在节点侧**，API 侧不新增该依赖
- `api/app/config.py`：`assistant_grpc_port=50052`、`assistant_node_tokens`（网关节点鉴权）、`assistant_model=claude-sonnet-5`、`assistant_daily_quota=100`、`assistant_run_sample_quota=20`
- 节点侧 env：`ANTHROPIC_API_KEY`（仅存节点，不进 API/git）、`SERVER_ADDRESS`/`SERVER_TOKEN`、联调可用 `ASSISTANT_MOCK=1` 走 mock 回显
- `deploy/docker-compose.yml`：**新增 `assistant-node` 服务**（非 privileged，无沙箱需求），key 从宿主 `.env` 注入
- 配额一期用 DB 计数（消息表按日 count），不为此引入 Redis 客户端

## 11. 分期与验收标准

**一期（本设计范围，约 3~5 天）**：§3~§9 全部 + 7 工具。
验收：① 题目页提问能带题面上下文流式回答；② 对一次真实 WA 提交，模型调用 get_submission/list_case_results 后给出针对性解释（人工评测 10 例）；③ **比赛中禁用抽测通过**：参赛者赛中调 `/assistant/chat` 一律 403、前端入口置灰，比赛结束后自动恢复；禁读清单与越权访问 404 亦在此列；④ 配额生效；⑤ pytest 全量绿 + 前端 build 过。

**二期**：出题者助手（题面审校/数据弱项报告）、回答与标程相似度检测、会话标题自动摘要、ADMIN 用量看板。

## 12. 风险与开放问题

- `run_on_sample` 复用网关 RunCode 通道需确认资源限额（建议 2s/64MB，比正式判题更紧）；
- 判题结果本身（逐点 diff 细节）暂不进工具——隐藏数据不泄露与诊断深度之间的折衷，二期可评估「只给失败点的输入规模特征」这类脱敏形式；
- token 成本：按日活与人均轮数估算后再定配额档位，首版 100 轮/人/日偏保守可调。
