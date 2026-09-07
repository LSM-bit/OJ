<template>
  <div class="home">
    <h1>OJ 在线评测</h1>
    <p>刷题 · 比赛 · 训练</p>
    <el-button type="primary" @click="$router.push('/problems')">开始刷题</el-button>
  </div>
</template>

<style scoped>
.home {
  text-align: center;
  padding: 80px 0;
}
</style>
