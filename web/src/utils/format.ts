/*
  format.ts - 通用格式化工具
  雪花 ID 太长（18~19 位），列表/表格里直接显示会换行：
  - shortId：截断显示为 #前8位…后4位，title 悬浮可看全量
  - fmtId：完整 ID 的等宽紧凑展示（详情页用）
*/

/** 雪花 ID 缩短显示：前 8 位 + … + 后 4 位（如 22292705…6384）；短 ID 原样返回 */
export function shortId(id: number | string | null | undefined): string {
  if (id === null || id === undefined || id === '') return ''
  const s = String(id)
  if (s.length <= 12) return s
  return `${s.slice(0, 8)}…${s.slice(-4)}`
}

/** 详情页等需要完整 ID 的场景：等宽字体紧凑显示（不截断） */
export function fmtId(id: number | string | null | undefined): string {
  if (id === null || id === undefined || id === '') return ''
  return String(id)
}
