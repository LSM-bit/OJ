<template>
  <div class="login">
    <el-card class="card">
      <h2>{{ isRegister ? '注册' : '登录' }}</h2>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" data-testid="username" />
        </el-form-item>
        <el-form-item v-if="isRegister">
          <el-input v-model="form.email" placeholder="邮箱" type="email" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" placeholder="密码" type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" style="width: 100%" :loading="loading">
            {{ isRegister ? '注册并登录' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <el-link type="primary" @click="isRegister = !isRegister">
        {{ isRegister ? '已有账号？去登录' : '没有账号？去注册' }}
      </el-link>
    </el-card>
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
.login { display: flex; justify-content: center; padding-top: 60px; }
.card { width: 400px; }
</style>
