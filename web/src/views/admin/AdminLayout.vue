<!--
  AdminLayout.vue - 管理后台框架
  左侧菜单（Dashboard/用户/题目/标签/比赛/题单/团队/提交/判题节点/AI 用量/公告管理/运行日志）+ 右侧内容区
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
        <el-menu-item index="/admin/ai-usage">
          <span>AI 用量</span>
        </el-menu-item>
        <el-menu-item index="/admin/announcements">
          <span>公告管理</span>
        </el-menu-item>
        <el-menu-item index="/admin/logs">
          <span>运行日志</span>
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
  border-right: 1px solid var(--oj-line);
  background: var(--oj-surface);
}
.admin-logo {
  padding: 16px;
  font-size: 17px;
  font-weight: 700;
  color: var(--el-color-primary);
  cursor: pointer;
  border-bottom: 1px solid var(--oj-line-soft);
}
.admin-menu {
  flex: 1;
  border-right: none;
}
.admin-back {
  padding: 10px 16px;
  border-top: 1px solid var(--oj-line-soft);
}
.admin-main {
  padding: 0;
  overflow: hidden;
}
/* ===== 视觉刷新：统一页面骨架（追加层，保证同特异性下胜出） ===== */
.page {
  padding: var(--oj-s5) var(--oj-s6) var(--oj-s8);
  box-sizing: border-box;
}
.page-head,
.head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--oj-s3);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s5);
}
.page-head h2,
.page-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.02em;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: var(--oj-s2);
  padding-bottom: var(--oj-s3);
  border-bottom: 1px solid var(--oj-line);
  margin-bottom: var(--oj-s4);
}
.spacer { flex: 1; }
.mono-id,
.mono {
  font-family: var(--oj-font-mono);
  font-size: var(--oj-fs-xs);
  font-variant-numeric: tabular-nums;
  color: var(--oj-ink-3);
}
.muted,
.tip,
.pick-hint,
.form-tip,
.data-hint,
.err-msg {
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.section { margin-top: var(--oj-s6); }
.section h4 {
  margin: 0 0 var(--oj-s3);
  font-size: var(--oj-fs-lg);
}
.stat-card {
  padding: var(--oj-s4) var(--oj-s5);
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease),
              transform var(--oj-dur-2) var(--oj-ease);
}
.stat-card:hover {
  border-color: var(--oj-line-strong);
  box-shadow: var(--oj-shadow-1);
  transform: translateY(-1px);
}
.stat-value {
  font-family: var(--oj-font-mono);
  font-size: 26px;
  letter-spacing: -0.02em;
  color: var(--oj-ink);
}
.stat-label {
  margin-top: 4px;
  color: var(--oj-ink-3);
  font-size: var(--oj-fs-sm);
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding: var(--oj-s3) 0;
}
.click-table,
.fill-table,
.cases-table,
.verify-table,
.log-list {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  overflow: hidden;
}

/* 管理后台 */
.admin-aside {
  background: var(--oj-surface-2);
  border-right: 1px solid var(--oj-line);
}
.admin-logo {
  font-family: var(--oj-font-display);
  letter-spacing: -0.01em;
}
.admin-logo,
.admin-back { border-bottom: 1px solid var(--oj-line-soft); }
.badges { display: flex; align-items: center; gap: var(--oj-s1); }
.log-list { background: var(--oj-surface); }
.log-row {
  transition: background var(--oj-dur-1) var(--oj-ease);
}
.log-time { font-family: var(--oj-font-mono); color: var(--oj-ink-4); }
.node-card {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
  transition: border-color var(--oj-dur-2) var(--oj-ease),
              box-shadow var(--oj-dur-2) var(--oj-ease);
}
.node-card:hover { border-color: var(--oj-line-strong); box-shadow: var(--oj-shadow-1); }
.chart {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  background: var(--oj-surface);
}
.rename-tip { color: var(--oj-ink-3); font-size: var(--oj-fs-sm); }
.preview {
  border: 1px solid var(--oj-line);
  border-radius: var(--oj-r3);
  padding: var(--oj-s3) var(--oj-s4);
}
</style>
