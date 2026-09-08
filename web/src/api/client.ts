/*
  client.ts - axios 实例：token 注入 + 401 跳登录 + 无损 JSON 解析
  雪花 ID 超出 JS Number 安全范围（2^53），普通 JSON.parse 会静默改写末几位
  （如 222985968074887168 → 222985968074887170），导致详情页"提交不存在"。
  用 json-bigint(storeAsString) 解析响应：大整数保留为字符串，小数字仍为 number。
*/
import axios from 'axios'
import JSONbig from 'json-bigint'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000',
  timeout: 15_000,
  transformResponse: [
    (data: string) => {
      if (typeof data !== 'string') return data
      if (!data) return null
      try {
        return JSONbig({ storeAsString: true }).parse(data)
      } catch {
        return JSON.parse(data) // 非 JSON 响应（如错误页）走原生解析
      }
    },
  ],
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('oj_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (resp) => resp.data,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('oj_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)
