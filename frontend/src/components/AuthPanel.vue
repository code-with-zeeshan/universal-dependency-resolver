<template>
  <div class="panel">
    <h2 class="panel-title">Authentication</h2>

    <div class="tabs mb-4">
      <button v-for="tab in authTabs" :key="tab.key" @click="activeTab = tab.key"
              class="tab" :class="{ 'tab-active': activeTab === tab.key }">
        {{ tab.label }}
      </button>
    </div>

    <div v-if="message" class="mb-4 p-3 rounded" :class="messageType === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'">
      {{ message }}
    </div>

    <!-- Login -->
    <div v-if="activeTab === 'login'" class="max-w-md mx-auto space-y-4">
      <input v-model="loginForm.username" placeholder="Username" class="form-input w-full" />
      <input v-model="loginForm.password" type="password" placeholder="Password" class="form-input w-full" @keyup.enter="doLogin" />
      <button @click="doLogin" class="btn btn-primary w-full" :disabled="authLoading">{{ authLoading ? 'Logging in...' : 'Login' }}</button>
    </div>

    <!-- Register -->
    <div v-if="activeTab === 'register'" class="max-w-md mx-auto space-y-4">
      <input v-model="regForm.username" placeholder="Username" class="form-input w-full" />
      <input v-model="regForm.email" type="email" placeholder="Email" class="form-input w-full" />
      <input v-model="regForm.password" type="password" placeholder="Password" class="form-input w-full" />
      <button @click="doRegister" class="btn btn-primary w-full" :disabled="authLoading">{{ authLoading ? 'Registering...' : 'Register' }}</button>
    </div>

    <!-- Profile -->
    <div v-if="activeTab === 'profile'" class="max-w-md mx-auto space-y-4">
      <div v-if="profile" class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <p><strong>Username:</strong> {{ profile.username }}</p>
        <p><strong>Full Name:</strong> {{ profile.full_name || '—' }}</p>
        <p><strong>Email:</strong> {{ profile.email }}</p>
        <p><strong>Active:</strong> {{ profile.is_active ? 'Yes' : 'No' }}</p>
      </div>
      <div class="border-t pt-4 space-y-3">
        <input v-model="profileForm.full_name" placeholder="Full name" class="form-input w-full" />
        <input v-model="profileForm.email" type="email" placeholder="Email" class="form-input w-full" />
        <button @click="updateProfile" class="btn btn-primary" :disabled="authLoading">Update Profile</button>
      </div>
    </div>

    <!-- API Keys -->
    <div v-if="activeTab === 'apikeys'" class="space-y-4">
      <div class="flex gap-2">
        <input v-model="newKeyName" placeholder="Key name" class="form-input flex-1" @keyup.enter="createApiKey" />
        <button @click="createApiKey" class="btn btn-primary" :disabled="authLoading">Create Key</button>
      </div>
      <div v-if="apiKeys && apiKeys.length > 0" class="space-y-2">
        <div v-for="key in apiKeys" :key="key.id"
             class="flex justify-between items-center p-3 bg-gray-50 rounded text-sm">
          <div>
            <p class="font-medium">{{ key.name }}</p>
            <p class="text-gray-500 text-xs">Created: {{ key.created_at }}</p>
          </div>
          <button @click="revokeApiKey(key.id)" class="text-red-600 hover:text-red-800 text-sm">Revoke</button>
        </div>
      </div>
      <div v-else-if="apiKeys" class="text-sm text-gray-500">No API keys yet.</div>
      <button @click="fetchApiKeys" class="btn btn-secondary text-sm">Refresh Keys</button>
    </div>

    <!-- Change Password -->
    <div v-if="activeTab === 'password'" class="max-w-md mx-auto space-y-4">
      <input v-model="pwForm.current" type="password" placeholder="Current password" class="form-input w-full" />
      <input v-model="pwForm.newPass" type="password" placeholder="New password" class="form-input w-full" />
      <input v-model="pwForm.confirm" type="password" placeholder="Confirm new password" class="form-input w-full" />
      <button @click="changePassword" class="btn btn-primary w-full" :disabled="authLoading">Change Password</button>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import authService from '../services/auth'

export default {
  name: 'AuthPanel',
  setup() {
    const authTabs = [
      { key: 'login', label: 'Login' },
      { key: 'register', label: 'Register' },
      { key: 'profile', label: 'Profile' },
      { key: 'apikeys', label: 'API Keys' },
      { key: 'password', label: 'Password' },
    ]
    const activeTab = ref(authService.isAuthenticated() ? 'profile' : 'login')
    const message = ref(null)
    const messageType = ref('error')
    const authLoading = ref(false)

    // Login
    const loginForm = ref({ username: '', password: '' })
    async function doLogin() {
      authLoading.value = true
      const result = await authService.login(loginForm.value)
      authLoading.value = false
      if (result.success) {
        message.value = 'Logged in successfully.'
        messageType.value = 'success'
        activeTab.value = 'profile'
        loadProfile()
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }

    // Register
    const regForm = ref({ username: '', email: '', password: '' })
    async function doRegister() {
      authLoading.value = true
      const result = await authService.register(regForm.value)
      authLoading.value = false
      if (result.success) {
        message.value = 'Registration successful. You can now log in.'
        messageType.value = 'success'
        activeTab.value = 'login'
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }

    // Profile
    const profile = ref(null)
    const profileForm = ref({ full_name: '', email: '' })
    async function loadProfile() {
      const result = await authService.getProfile()
      if (result.success) {
        profile.value = result.user
        profileForm.value = { full_name: result.user.full_name || result.user.username || '', email: result.user.email || '' }
      }
    }
    async function updateProfile() {
      authLoading.value = true
      const result = await authService.updateProfile(profileForm.value)
      authLoading.value = false
      if (result.success) {
        message.value = 'Profile updated.'
        messageType.value = 'success'
        profile.value = result.user
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }

    // API Keys
    const apiKeys = ref(null)
    const newKeyName = ref('')
    async function fetchApiKeys() {
      const result = await authService.getApiKeys()
      if (result.success) {
        apiKeys.value = result.keys
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }
    async function createApiKey() {
      if (!newKeyName.value) return
      authLoading.value = true
      const result = await authService.createApiKey({ name: newKeyName.value })
      authLoading.value = false
      if (result.success) {
        message.value = 'API key created.'
        messageType.value = 'success'
        newKeyName.value = ''
        fetchApiKeys()
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }
    async function revokeApiKey(keyId) {
      authLoading.value = true
      const result = await authService.revokeApiKey(keyId)
      authLoading.value = false
      if (result.success) {
        fetchApiKeys()
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }

    // Change Password
    const pwForm = ref({ current: '', newPass: '', confirm: '' })
    async function changePassword() {
      if (pwForm.value.newPass !== pwForm.value.confirm) {
        message.value = 'Passwords do not match.'
        messageType.value = 'error'
        return
      }
      authLoading.value = true
      const result = await authService.changePassword({
        current_password: pwForm.value.current,
        new_password: pwForm.value.newPass,
      })
      authLoading.value = false
      if (result.success) {
        message.value = 'Password changed.'
        messageType.value = 'success'
        pwForm.value = { current: '', newPass: '', confirm: '' }
      } else {
        message.value = result.error
        messageType.value = 'error'
      }
    }

    onMounted(() => {
      if (authService.isAuthenticated()) {
        loadProfile()
        fetchApiKeys()
      }
    })

    return {
      authTabs, activeTab, message, messageType, authLoading,
      loginForm, doLogin,
      regForm, doRegister,
      profile, profileForm, loadProfile, updateProfile,
      apiKeys, newKeyName, fetchApiKeys, createApiKey, revokeApiKey,
      pwForm, changePassword,
    }
  }
}
</script>
