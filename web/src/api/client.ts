import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? 'http://localhost:8000',
  timeout: 15_000,
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
