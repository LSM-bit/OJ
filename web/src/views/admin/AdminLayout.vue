<!--
  AdminLayout.vue - 管理后台框架
  左侧菜单（Dashboard/用户/题目/标签/比赛/题单/团队/提交/判题节点）+ 右侧内容区
  入口控制：仅作为体验层，真正校验在后端 /admin/* 组级 require_admin
-->
<template>
  <div class="admin-layout">
    <el-aside class="admin-aside" width="200px">
      <div class="admin-logo" @click="$router.push('/')">OJ 后台</div>
      <el-menu router :default-active="route.path" class="admin-menu">
        <el-menu-item index="/admin">
          <span>站点概况</span>
        </el-menu-item>
        <el-menu-item index="/admin/users">
          <span>用户管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/problems">
          <span>题目管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/tags">
          <span>标签管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/contests">
          <span>比赛管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/playlists">
          <span>题单管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/teams">
          <span>团队管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/submissions">
          <span>提交管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/judges">
          <span>判题节点</span>
        </el-menu-item>
      </el-menu>
      <div class="admin-back">
        <el-button text size="small" @click="$router.push('/')">← 返回前台</el-button>
      </div>
    </el-aside>
    <el-main class="admin-main">
      <router-view />
    </el-main>
  </div>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<style scoped>
.admin-layout {
  height: 100%;
  display: flex;
}
.admin-aside {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--el-border-color-light);
  background: #fff;
}
.admin-logo {
  padding: 16px;
  font-size: 17px;
  font-weight: 700;
  color: var(--el-color-primary);
  cursor: pointer;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.admin-menu {
  flex: 1;
  border-right: none;
}
.admin-back {
  padding: 10px 16px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.admin-main {
  padding: 0;
  overflow: hidden;
}
</style>
