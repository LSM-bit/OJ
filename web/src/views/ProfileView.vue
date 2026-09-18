<!--
  ProfileView.vue - 个人中心
  /profile：铺满页面两栏布局。左栏展示头像/用户名/角色/Rating，支持上传/移除头像；
  右栏「基本信息」表单（用户名/邮箱，一起提交 PATCH /users/me）；
  「修改密码」独立弹窗（旧密码 + 新密码，二次确认），与资料编辑互不影响
-->
<template>
  <div class="page">
    <header class="page-head">
      <div class="head-titles">
        <span class="oj-kicker">Profile</span>
        <h2>个人中心</h2>
      </div>
    </header>

    <div class="grid">
      <!-- 左栏：头像 + 基础身份展示 -->
      <div class="col">
        <el-card class="card">
          <template #header><span class="card-title">我的头像</span></template>
          <div class="avatar-box">
            <el-upload :show-file-list="false" :before-upload="beforeAvatarUpload"
                       :http-request="doUploadAvatar"
                       accept="image/jpeg,image/png,image/webp,image/gif">
              <el-avatar :size="96" :src="avatarUrl || undefined" class="big-avatar">
                {{ avatarChar }}
              </el-avatar>
            </el-upload>
            <div class="avatar-hint">点击头像上传（jpg/png/webp/gif，≤2MB）</div>
            <el-button v-if="avatarUrl" size="small" text type="danger" @click="removeAvatar">
              恢复默认头像
            </el-button>
          </div>

          <el-divider />

          <div class="identity">
            <div class="username">{{ userStore.user?.username }}</div>
            <div class="meta">
              <el-tag :type="userStore.user?.role === 'admin' ? 'danger' : 'info'" size="small">
                {{ userStore.user?.role === 'admin' ? '管理员' : '普通用户' }}
              </el-tag>
              <span class="rating">Rating {{ userStore.user?.rating }}</span>
            </div>
          </div>
        </el-card>
      </div>

      <!-- 右栏：编辑全部信息（一起提交） -->
      <div class="col">
        <el-card class="card">
          <template #header><span class="card-title">编辑资料</span></template>
          <el-form label-width="90px" label-position="left">
            <el-form-item label="用户名">
              <el-input v-model="form.username" maxlength="32" placeholder="2-32 位字母数字_-"
                        data-testid="profile-username" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="form.email" placeholder="邮箱" data-testid="profile-email" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="saving" data-testid="profile-save"
                         @click="saveProfile">
                保存修改
              </el-button>
              <el-button @click="openPasswordDialog">修改密码</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="420" align-center
               @closed="resetPwdForm">
      <el-form label-width="90px" label-position="left">
        <el-form-item label="旧密码">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password
                    placeholder="当前密码" data-testid="pwd-old" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="pwdForm.newPassword" type="password" show-password
                    placeholder="不少于 6 位" data-testid="pwd-new" />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="pwdForm.confirm" type="password" show-password
                    placeholder="再输入一遍新密码" data-testid="pwd-confirm" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPwd" data-testid="pwd-submit"
                   @click="savePassword">确认修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
// 头像 URL 拼接：后端返回相对路径 /static/avatars/xxx，浏览器需完整地址
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import { api } from '../api/client'
import { useUserStore } from '../stores/user'

const userStore = useUserStore()

// 头像字符：用户名首字母（无头像时的兜底展示）
const avatarChar = computed(() =>
  (userStore.user?.username ?? '?').charAt(0).toUpperCase())
const avatarUrl = computed(() => {
  const a = userStore.user?.avatar
  return a ? `${api.defaults.baseURL}${a}` : ''
})

// ---------------- 资料编辑（用户名 + 邮箱一起提交） ----------------
const form = reactive({ username: '', email: '' })
const saving = ref(false)

onMounted(async () => {
  if (!userStore.user) await userStore.fetchMe()
  fillForm()
})

function fillForm() {
  if (userStore.user) {
    form.username = userStore.user.username
    form.email = userStore.user.email
  }
}

async function saveProfile() {
  const username = form.username.trim()
  const email = form.email.trim()
  if (!username) return ElMessage.warning('请填写用户名')
  if (!email) return ElMessage.warning('请填写邮箱')
  saving.value = true
  try {
    userStore.user = await api.patch('/users/me', { username, email }) as any
    ElMessage.success('资料已更新')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

// ---------------- 修改密码（独立弹窗） ----------------
const pwdVisible = ref(false)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirm: '' })
const savingPwd = ref(false)

function openPasswordDialog() {
  pwdVisible.value = true
}

function resetPwdForm() {
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirm = ''
}

async function savePassword() {
  if (!pwdForm.oldPassword) return ElMessage.warning('请输入当前密码')
  if (!pwdForm.newPassword || pwdForm.newPassword.length < 6)
    return ElMessage.warning('新密码不少于 6 位')
  if (pwdForm.newPassword !== pwdForm.confirm)
    return ElMessage.warning('两次输入的新密码不一致')
  savingPwd.value = true
  try {
    await api.patch('/users/me', {
      old_password: pwdForm.oldPassword,
      new_password: pwdForm.newPassword,
    })
    ElMessage.success('密码已修改')
    pwdVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '修改失败')
  } finally {
    savingPwd.value = false
  }
}

// ---------------- 头像上传 ----------------
function beforeAvatarUpload(file: File) {
  const okType = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'].includes(file.type)
  if (!okType) {
    ElMessage.error('仅支持 jpg/png/webp/gif 图片')
    return false
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.error('头像不能超过 2MB')
    return false
  }
  return true
}

async function doUploadAvatar(options: UploadRequestOptions) {
  const fd = new FormData()
  fd.append('file', options.file)
  try {
    userStore.user = await api.post('/users/me/avatar', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as any
    ElMessage.success('头像已更新')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '上传失败')
  }
}

async function removeAvatar() {
  try {
    userStore.user = await api.delete('/users/me/avatar') as any
    ElMessage.success('已恢复默认头像')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? '操作失败')
  }
}
</script>

<style scoped>
/* 铺满页面：占满 el-main 高度（main 有 overflow:hidden，100% 即视口减顶栏），
   两栏等宽撑满宽度；卡片撑满列高 */
.page {
  height: 100%;
  padding: 16px 20px;
  box-sizing: border-box;
  overflow-y: auto;
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1.4fr;
  gap: 16px;
  height: 100%;
  min-height: 520px; /* 小屏兜底：内容不足时保持可读高度 */
}
.col { display: flex; flex-direction: column; }
.card {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.card :deep(.el-card__body) { flex: 1; }
.card-title { font-weight: 600; }

.avatar-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
}
.big-avatar {
  background: var(--el-color-primary);
  color: #fff;
  font-size: 40px;
  font-weight: 600;
  cursor: pointer;
}
.avatar-hint {
  font-size: 12px;
  color: var(--oj-ink-3);
}
.identity { text-align: center; padding-bottom: 8px; }
.identity .username { font-size: 22px; font-weight: 600; }
.identity .meta {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.rating { color: var(--oj-ink-3); font-size: 13px; }
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

/* ===== 逻辑复查：统一标题区 ===== */
.head-titles { display: flex; flex-direction: column; gap: 2px; }
.head-titles h2 { margin: 0; font-size: 26px; letter-spacing: -0.02em; }
</style>
