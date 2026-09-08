/*
  copyCodeHandler.ts - 题面代码块复制按钮的全局点击处理
  采用事件委托：各页面 v-html 渲染的 Markdown 代码块（.code-copy-btn）
  点击后把同容器内 <pre><code> 文本复制到剪贴板。
  在 main.ts 里 document 级注册一次即可，页面无需各自挂事件。
*/

function bindCodeCopy() {
  document.addEventListener('click', async (ev) => {
    const target = ev.target as HTMLElement
    const btn = target.closest?.('[data-code-copy]') as HTMLElement | null
    if (!btn) return
    const block = btn.closest('.code-block')
    const code = block?.querySelector('pre code, pre')?.textContent ?? ''
    if (!code) return
    try {
      await navigator.clipboard.writeText(code)
      const old = btn.textContent
      btn.textContent = '已复制'
      btn.classList.add('copied')
      setTimeout(() => {
        btn.textContent = old
        btn.classList.remove('copied')
      }, 1200)
    } catch {
      btn.textContent = '复制失败'
      setTimeout(() => (btn.textContent = '复制'), 1200)
    }
  })
}

export function setupCodeCopy() {
  if (typeof document !== 'undefined') bindCodeCopy()
}
