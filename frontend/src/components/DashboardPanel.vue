<template>
  <div class="panel">
    <h2 class="panel-title">Dashboard</h2>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      <div class="stat-card" v-if="health">
        <div class="stat-label">API Status</div>
        <div class="stat-value" :class="health.status === 'healthy' ? 'text-green-600' : 'text-red-600'">
          {{ health.status }}
        </div>
      </div>
      <div class="stat-card" v-if="health?.checks?.database">
        <div class="stat-label">Database</div>
        <div class="stat-value" :class="health.checks.database.status === 'healthy' ? 'text-green-600' : 'text-red-600'">
          {{ health.checks.database.status }}
        </div>
      </div>
      <div class="stat-card" v-if="systemInfo">
        <div class="stat-label">Platform</div>
        <div class="stat-value text-sm">{{ systemInfo.platform?.system }} {{ systemInfo.platform?.release }}</div>
      </div>
      <div class="stat-card" v-if="systemInfo?.cpu">
        <div class="stat-label">CPU</div>
        <div class="stat-value text-sm">{{ systemInfo.cpu.brand }}</div>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6" v-if="systemInfo">
      <div class="stat-card" v-if="systemInfo.memory">
        <div class="stat-label">Memory</div>
        <div class="stat-value text-sm">{{ formatBytes(systemInfo.memory.total) }} total / {{ formatBytes(systemInfo.memory.available) }} free</div>
      </div>
      <div class="stat-card" v-if="systemInfo.gpu">
        <div class="stat-label">GPU</div>
        <div class="stat-value text-sm" v-if="systemInfo.gpu.available">
          {{ systemInfo.gpu.devices?.[0]?.name || 'Available' }}
          <span v-if="systemInfo.gpu.cuda" class="ml-2 text-xs text-gray-500">CUDA {{ systemInfo.gpu.cuda }}</span>
        </div>
        <div class="stat-value text-sm text-gray-500" v-else>Not detected</div>
      </div>
    </div>

    <div class="bg-gray-50 rounded-lg p-4 mb-4">
      <h3 class="font-semibold mb-3">Quick Actions</h3>
      <div class="flex flex-wrap gap-3">
        <button @click="$emit('navigate', 'resolve')" class="btn btn-primary text-sm">
          Resolve Dependencies
        </button>
        <button @click="$emit('navigate', 'packages')" class="btn btn-secondary text-sm">
          Search Packages
        </button>
        <button @click="$emit('navigate', 'system')" class="btn btn-secondary text-sm">
          System Details
        </button>
        <button @click="refreshHealth" class="btn btn-secondary text-sm" :disabled="loading">
          {{ loading ? 'Refreshing...' : 'Refresh Status' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-msg">{{ error }}</div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import systemService from '../services/systemService'

export default {
  name: 'DashboardPanel',
  emits: ['navigate'],
  setup() {
    const health = ref(null)
    const systemInfo = ref(null)
    const loading = ref(false)
    const error = ref(null)

    async function fetchHealth() {
      try {
        health.value = await systemService.getHealthStatus()
      } catch (e) {
        health.value = { status: 'unreachable' }
      }
    }

    async function fetchSystemInfo() {
      try {
        systemInfo.value = await systemService.getSystemInfo(true)
      } catch (e) {
        // silent
      }
    }

    async function refreshHealth() {
      loading.value = true
      error.value = null
      await Promise.all([fetchHealth(), fetchSystemInfo()])
      loading.value = false
    }

    function formatBytes(bytes) {
      if (!bytes) return 'Unknown'
      const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
      const i = Math.floor(Math.log(bytes) / Math.log(1024))
      return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i]
    }

    onMounted(() => {
      fetchHealth()
      fetchSystemInfo()
    })

    return { health, systemInfo, loading, error, refreshHealth, formatBytes }
  }
}
</script>
