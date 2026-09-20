// router/index.ts - 前端路由表
// /admin/* 整组 requiresAdmin，守卫里仅做入口控制（真正校验在后端 require_admin）
import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // 主页（独立首页：概览 + 每日打卡 + 快捷入口 + 最新题目）
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/home', redirect: '/' },
    // 刷题（公开题目）
    { path: '/problems', name: 'problems', component: () => import('../views/ProblemsView.vue') },
    { path: '/problems/:id', name: 'problem-detail', component: () => import('../views/ProblemDetailView.vue') },
    // 出题（创作视角，含草稿）
    { path: '/manage', name: 'manage', component: () => import('../views/ProblemManageView.vue') },
    { path: '/problems/new', name: 'problem-new', component: () => import('../views/ProblemEditView.vue') },
    { path: '/problems/:id/edit', name: 'problem-edit', component: () => import('../views/ProblemEditView.vue') },
    { path: '/contests', name: 'contests', component: () => import('../views/ContestsView.vue') },
    { path: '/contests/new', name: 'contest-new', component: () => import('../views/ContestEditView.vue') },
    // 创建比赛第二步：选择题目（独立页，支持标签筛选 / 题号标题搜索 / 分页）
    { path: '/contests/new/pick', name: 'contest-new-pick', component: () => import('../views/ContestProblemPickView.vue') },
    { path: '/contests/:id', name: 'contest-detail', component: () => import('../views/ContestDetailView.vue') },
    { path: '/contests/:id/problems/:alias', name: 'contest-problem', component: () => import('../views/ContestProblemView.vue') },
    { path: '/teams', name: 'teams', component: () => import('../views/TeamsView.vue') },
    { path: '/playlists', name: 'playlists', component: () => import('../views/PlaylistsView.vue') },
    { path: '/manage/playlists', name: 'manage-playlists', component: () => import('../views/PlaylistsView.vue') },
    { path: '/playlists/:id', name: 'playlist-detail', component: () => import('../views/PlaylistsView.vue') },
    { path: '/playlists/:id/problems/:pid', name: 'playlist-problem', component: () => import('../views/PlaylistProblemView.vue') },
    { path: '/submissions', name: 'submissions', component: () => import('../views/SubmissionsView.vue') },
    { path: '/submissions/:id', name: 'submission-detail', component: () => import('../views/SubmissionDetailView.vue') },
    // 个人中心：展示/编辑资料、上传头像
    { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue') },
    {
      path: '/admin',
      component: () => import('../views/admin/AdminLayout.vue'),
      meta: { requiresAdmin: true },
      children: [
        { path: '', name: 'admin-dashboard', component: () => import('../views/admin/DashboardView.vue') },
        { path: 'users', name: 'admin-users', component: () => import('../views/admin/AdminUsers.vue') },
        { path: 'problems', name: 'admin-problems', component: () => import('../views/admin/AdminProblems.vue') },
        { path: 'tags', name: 'admin-tags', component: () => import('../views/admin/AdminTags.vue') },
        { path: 'contests', name: 'admin-contests', component: () => import('../views/admin/AdminContests.vue') },
        { path: 'playlists', name: 'admin-playlists', component: () => import('../views/admin/AdminPlaylists.vue') },
        { path: 'teams', name: 'admin-teams', component: () => import('../views/admin/AdminTeams.vue') },
        { path: 'submissions', name: 'admin-submissions', component: () => import('../views/admin/AdminSubmissions.vue') },
        { path: 'judges', name: 'admin-judges', component: () => import('../views/admin/AdminJudges.vue') },
        { path: 'ai-usage', name: 'admin-ai-usage', component: () => import('../views/admin/AdminAiUsage.vue') },
        { path: 'announcements', name: 'admin-announcements', component: () => import('../views/admin/AdminAnnouncements.vue') },
        { path: 'logs', name: 'admin-logs', component: () => import('../views/admin/AdminLogs.vue') },
      ],
    },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  ],
})

// 守卫：非 ADMIN 访问 /admin/* 跳首页（体验层，后端仍强校验）
// 注意：刷新页面时 Pinia 里只有 token、还没有用户信息，必须先 await fetchMe 再判定，
// 否则 admin 刷新后台页会被误判为未登录而弹回首页（要求：刷新停留在当前页面）
router.beforeEach(async (to) => {
  if (to.meta.requiresAdmin) {
    const userStore = useUserStore()
    if (userStore.token && !userStore.user) {
      try {
        await userStore.fetchMe()
      } catch {
        // 令牌失效或网络异常：按未登录处理，交给下面的判定
      }
    }
    if (userStore.user?.role !== 'admin') return '/'
  }
})

export default router
