/*
  markdown.ts - Markdown 渲染共享工具
  markdown-it 基础渲染 + KaTeX 数学公式支持（$...$ 行内、$$...$$ 块级）
  代码块外包 .code-block 容器并注入复制按钮（题面样例可一键复制）
  题目描述、比赛题面、清单题面共用此实例
*/
import markdownit from 'markdown-it'
// 该包的 CJS/ESM 互操作有双层 default 包装，需解包出真正的插件函数
import katexWrap from '@vscode/markdown-it-katex'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const katex: any = (katexWrap as any).default ?? katexWrap

const md = markdownit({ html: false, linkify: true })
md.use(katex)

// 代码块加 .code-block 包装 + 复制按钮（按钮行为由全局事件委托处理，见 copyCodeHandler.ts）
const defaultFence =
  md.renderer.rules.fence ??
  ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.fence = (tokens, idx, options, env, self) => {
  const inner = defaultFence(tokens, idx, options, env, self)
  return (
    `<div class="code-block">` +
    `<button type="button" class="code-copy-btn" data-code-copy>复制</button>` +
    inner +
    `</div>`
  )
}

export default md
