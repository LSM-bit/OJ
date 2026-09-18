import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'katex/dist/katex.min.css'
import App from './App.vue'
import router from './router'
import { setupCodeCopy } from './utils/copyCodeHandler'
import './style.css'
// 设计系统：必须最后加载，用于覆盖 Element Plus 默认主题变量与组件观感
import './design-system.css'

// 题面代码块「复制」按钮的全局事件委托（各页面 v-html 内容通用）
setupCodeCopy()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
