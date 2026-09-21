import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
// 子路径部署：生产构建挂在 /oj/ 下（对外入口 http://<ip>/oj/），dev 仍用根路径，
// 开发时无需输入 /oj/ 前缀；两者都会把 base 输出成 import.meta.env.BASE_URL，
// vue-router 的 createWebHistory(base) 与它保持一致即可（见 src/router/index.ts）。
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/oj/' : '/',
  plugins: [vue()],
}))
