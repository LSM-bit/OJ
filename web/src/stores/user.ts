import { defineStore } from 'pinia'
import { api } from '../api/client'

export interface UserInfo {
  id: number
  username: string
  email: string
  role: string
  rating: number
  avatar: string | null
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('oj_token') || '',
    user: null as UserInfo | null,
  }),
  getters: {
    isLoggedIn: (s) => !!s.token,
  },
  actions: {
    async fetchMe() {
      // 有 token 但内存里没有用户信息（如刷新页面后）时拉取
      if (!this.token || this.user) return
      this.user = await api.get('/users/me')
    },
    async login(username: string, password: string) {
      const data: any = await api.post('/users/login', { username, password })
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('oj_token', this.token)
    },
    async register(username: string, email: string, password: string) {
      await api.post('/users/register', { username, email, password })
      await this.login(username, password)
    },
    logout() {
      this.token = ''
      this.user = null
      localStorage.removeItem('oj_token')
    },
  },
})
