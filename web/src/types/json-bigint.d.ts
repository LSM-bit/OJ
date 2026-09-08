/*
  json-bigint.d.ts - json-bigint 的 TS 类型声明
  该包无官方类型；本项目只用其 { storeAsString: true } 工厂形式：
  创建把超出 JS 安全整数范围的数字解析为字符串的解析器（雪花 ID 防精度丢失）
*/
declare module 'json-bigint' {
  interface JSONBigOptions {
    /** 超出安全整数的数字存为字符串（而非 BigNumber 对象） */
    storeAsString?: boolean
    /** 使用原生 bigint 而非 BigNumber */
    useNativeBigInt?: boolean
    /** 始终用 BigNumber 解析（默认行为） */
    alwaysParseAsBig?: boolean
    /** 原型污染防护键名 */
    protoAction?: 'error' | 'ignore' | 'preserve'
    constructorAction?: 'error' | 'ignore' | 'preserve'
  }

  interface JSONBig {
    parse(text: string): unknown
    stringify(value: unknown, replacer?: unknown, space?: unknown): string
  }

  function jsonBig(options?: JSONBigOptions): JSONBig

  namespace jsonBig {
    /** 无参默认实例：解析结果为 BigNumber 对象 */
    export function parse(text: string): unknown
    export function stringify(value: unknown, replacer?: unknown, space?: unknown): string
  }

  export default jsonBig
}
