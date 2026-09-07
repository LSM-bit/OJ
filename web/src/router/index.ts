import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: () => import('../views/HomeView.vue') },
    { path: '/problems', name: 'problems', component: () => import('../views/ProblemsView.vue') },
    { path: '/problems/:id', name: 'problem-detail', component: () => import('../views/ProblemDetailView.vue') },
    { path: '/contests', name: 'contests', component: () => import('../views/ContestsView.vue') },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue') },
  ],
})

export default router
