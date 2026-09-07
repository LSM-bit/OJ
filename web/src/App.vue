<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from './stores/user'

const router = useRouter()
const userStore = useUserStore()

function logout() {
  userStore.logout()
  router.push('/')
}
</script>

<template>
  <el-container class="layout">
    <el-header class="header">
      <div class="logo" @click="router.push('/')">OJ</div>
      <el-menu mode="horizontal" router :default-active="$route.path" :ellipsis="false">
        <el-menu-item index="/problems">题目</el-menu-item>
        <el-menu-item index="/contests">比赛</el-menu-item>
      </el-menu>
      <div class="spacer" />
      <template v-if="userStore.isLoggedIn">
        <span class="username">{{ userStore.user?.username }}</span>
        <el-button text @click="logout">退出</el-button>
      </template>
      <el-button v-else text @click="router.push('/login')">登录 / 注册</el-button>
    </el-header>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.header {
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--el-border-color-light);
}
.logo {
  font-size: 22px;
  font-weight: 700;
  cursor: pointer;
  color: var(--el-color-primary);
}
.spacer {
  flex: 1;
}
</style>
