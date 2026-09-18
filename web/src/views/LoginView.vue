<template>
  <div class="auth">
    <!-- 左：品牌陈述 -->
    <section class="auth-aside">
      <div class="aside-top">
        <span class="aside-mark">衡</span>
        <span class="aside-kicker">Online Judge</span>
      </div>

      <div class="aside-body">
        <h1>把每一行代码，<br />交给秤来称</h1>
        <p>题库、竞赛、题单、团队与 AI 助教，收敛在同一套评测系统里。</p>
      </div>

      <ul class="aside-facts">
        <li><b>nsjail</b> 沙箱隔离</li>
        <li><b>C++ / Java / C</b> 多语言评测</li>
        <li><b>实时</b> 榜单与提交回放</li>
      </ul>
    </section>

    <!-- 右：表单 -->
    <section class="auth-main">
      <div class="auth-card">
        <span class="oj-kicker">{{ isRegister ? 'Create account' : 'Sign in' }}</span>
        <h2>{{ isRegister ? '注册账号' : '登录' }}</h2>
        <p class="auth-hint">{{ isRegister ? '注册后即可提交代码与参加竞赛' : '使用用户名与密码继续' }}</p>

        <form @submit.prevent="submit">
          <label class="field">
            <span>用户名</span>
            <el-input v-model="form.username" placeholder="用户名" size="large"
                      data-testid="username" />
          </label>
          <label v-if="isRegister" class="field">
            <span>邮箱</span>
            <el-input v-model="form.email" placeholder="邮箱" type="email" size="large" />
          </label>
          <label class="field">
            <span>密码</span>
            <el-input v-model="form.password" placeholder="密码" type="password" size="large"
                      show-password />
          </label>
          <button class="submit" type="submit" :disabled="loading">
            {{ loading ? '处理中…' : (isRegister ? '注册并登录' : '登录') }}
          </button>
        </form>

        <div class="auth-switch">
          <span>{{ isRegister ? '已有账号？' : '还没有账号？' }}</span>
          <el-link type="primary" :underline="false" @click="isRegister = !isRegister">
            {{ isRegister ? '去登录' : '去注册' }}
          </el-link>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'

const router = useRouter()
const userStore = useUserStore()
const isRegister = ref(false)
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '' })

async function submit() {
  if (!form.username || !form.password) {
    ElMessage.warning('请填写用户名和密码')
    return
  }
  loading.value = true
  try {
    if (isRegister.value) {
      await userStore.register(form.username, form.email, form.password)
    } else {
      await userStore.login(form.username, form.password)
    }
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 两栏：左侧品牌墨底，右侧表单 */
.auth {
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
  background: var(--oj-paper);
}

/* ------------------------------------------------------------- 品牌侧 */
.auth-aside {
  position: relative;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: var(--oj-s8) var(--oj-s8) var(--oj-s7);
  /* 两种配色模式下都为深墨底，保证品牌侧恒定 */
  background: oklch(24% 0.020 264);
  color: oklch(96% 0.006 80);
  overflow: hidden;
}
/* 细分网格纹理：技术图纸感，仅在左侧大面积处使用一次 */
.auth-aside::before {
  content: '';
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(to right, oklch(100% 0 0 / 0.045) 1px, transparent 1px),
    linear-gradient(to bottom, oklch(100% 0 0 / 0.045) 1px, transparent 1px);
  background-size: 44px 44px;
  pointer-events: none;
}
.aside-top { position: relative; display: flex; align-items: center; gap: 10px; }
.aside-mark {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: 1px solid oklch(100% 0 0 / 0.28);
  border-radius: var(--oj-r1);
  font-size: 15px;
  font-weight: 700;
}
.aside-kicker {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: oklch(100% 0 0 / 0.62);
}

.aside-body { position: relative; max-width: 460px; }
.aside-body h1 {
  font-size: clamp(30px, 3.2vw, 46px);
  line-height: 1.16;
  font-weight: 600;
  letter-spacing: -0.025em;
  color: oklch(98% 0.004 80);
  margin: 0;
}
.aside-body p {
  margin-top: var(--oj-s4);
  font-size: var(--oj-fs-lg);
  line-height: 1.7;
  color: oklch(100% 0 0 / 0.66);
}

.aside-facts {
  position: relative;
  list-style: none;
  margin: 0;
  padding: var(--oj-s4) 0 0;
  border-top: 1px solid oklch(100% 0 0 / 0.16);
  display: flex;
  flex-wrap: wrap;
  gap: var(--oj-s2) var(--oj-s6);
  font-size: var(--oj-fs-sm);
  color: oklch(100% 0 0 / 0.55);
}
.aside-facts b {
  font-family: var(--oj-font-mono);
  font-weight: 600;
  color: oklch(100% 0 0 / 0.88);
}

/* --------------------------------------------------------------- 表单侧 */
.auth-main {
  display: grid;
  place-items: center;
  padding: var(--oj-s6);
}
.auth-card { width: 100%; max-width: 380px; }
.auth-card h2 {
  margin-top: 6px;
  font-size: 28px;
  letter-spacing: -0.02em;
}
.auth-hint {
  margin-top: 6px;
  font-size: var(--oj-fs-md);
  color: var(--oj-ink-3);
}

form {
  margin-top: var(--oj-s6);
  display: flex;
  flex-direction: column;
  gap: var(--oj-s4);
}
.field { display: flex; flex-direction: column; gap: 6px; }
.field > span {
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-xs);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--oj-ink-3);
}

.submit {
  margin-top: var(--oj-s2);
  height: 46px;
  border: 0;
  border-radius: var(--oj-r2);
  background: var(--oj-accent);
  color: #fff;
  font-family: var(--oj-font-display);
  font-size: var(--oj-fs-lg);
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: background-color var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-1) var(--oj-ease);
}
.submit:hover:not(:disabled) { background: var(--oj-accent-deep); }
.submit:active:not(:disabled) { transform: translateY(1px); }
.submit:disabled { opacity: 0.55; cursor: default; }

.auth-switch {
  margin-top: var(--oj-s5);
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--oj-fs-md);
  color: var(--oj-ink-3);
}

/* 窄屏收成单栏：品牌侧让位给表单 */
@media (max-width: 900px) {
  .auth { grid-template-columns: 1fr; }
  .auth-aside { display: none; }
}
</style>
