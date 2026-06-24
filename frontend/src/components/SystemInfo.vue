<template>
  <div class="system-info">
    <div class="info-header">
      <h3>System Information</h3>
      <button @click="refresh" :disabled="loading" class="refresh-button">
        <RefreshIcon :class="{ 'animate-spin': loading }" />
        {{ loading ? 'Scanning...' : 'Refresh' }}
      </button>
    </div>
    
    <div v-if="systemInfo" class="info-grid">
      <!-- OS Info -->
      <div class="info-card">
        <div class="info-title">
          <ComputerIcon />
          Operating System
        </div>
        <div class="info-content">
          <p><strong>System:</strong> {{ systemInfo.platform?.system }}</p>
          <p><strong>Release:</strong> {{ systemInfo.platform?.release }}</p>
          <p><strong>Architecture:</strong> {{ systemInfo.platform?.machine }}</p>
        </div>
      </div>
      
      <!-- CPU Info -->
      <div class="info-card">
        <div class="info-title">
          <CpuIcon />
          CPU
        </div>
        <div class="info-content">
          <p><strong>Model:</strong> {{ systemInfo.cpu?.brand || 'Unknown' }}</p>
          <p><strong>Cores:</strong> {{ systemInfo.cpu?.count || 0 }} ({{ systemInfo.cpu?.count_logical || 0 }} logical)</p>
          <p><strong>Architecture:</strong> {{ systemInfo.cpu?.arch }}</p>
        </div>
      </div>
      
      <!-- GPU Info -->
      <div class="info-card" :class="{ 'gpu-not-available': !systemInfo.gpu?.available }">
        <div class="info-title">
          <GpuIcon />
          GPU
        </div>
        <div class="info-content">
          <template v-if="systemInfo.gpu?.available">
            <p><strong>Model:</strong> {{ systemInfo.gpu.devices[0]?.name }}</p>
            <p><strong>Memory:</strong> {{ formatGpuMemory(systemInfo.gpu.devices[0]) }}</p>
            <p><strong>CUDA:</strong> {{ systemInfo.gpu.cuda || 'Not installed' }}</p>
            <p v-if="systemInfo.gpu.cudnn"><strong>cuDNN:</strong> {{ systemInfo.gpu.cudnn }}</p>
          </template>
          <template v-else>
            <p class="text-gray-500">No GPU detected</p>
          </template>
        </div>
      </div>
      
      <!-- Runtime Versions -->
      <div class="info-card">
        <div class="info-title">
          <CodeIcon />
          Runtime Versions
        </div>
        <div class="info-content">
          <p v-if="systemInfo.runtime_versions?.python">
            <strong>Python:</strong> {{ systemInfo.runtime_versions.python.version }}
          </p>
          <p v-if="systemInfo.runtime_versions?.node">
            <strong>Node.js:</strong> {{ systemInfo.runtime_versions.node.version }}
          </p>
          <p v-if="systemInfo.runtime_versions?.gcc">
            <strong>GCC:</strong> {{ systemInfo.runtime_versions.gcc.version }}
          </p>
          <p v-if="systemInfo.runtime_versions?.java">
            <strong>Java:</strong> {{ systemInfo.runtime_versions.java.version }}
          </p>
        </div>
      </div>
    </div>
    
    <div v-else class="no-info">
      <p>System information not yet loaded</p>
      <button @click="refresh" class="btn btn-primary">
        Scan System
      </button>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import systemService from '../services/systemService'
import { 
  RefreshIcon, 
  ComputerIcon, 
  CpuIcon, 
  GpuIcon, 
  CodeIcon 
} from '../icons'

export default {
  name: 'SystemInfo',
  components: {
    RefreshIcon,
    ComputerIcon,
    CpuIcon,
    GpuIcon,
    CodeIcon
  },
  emits: ['system-updated'],
  setup(props, { emit }) {
    const systemInfo = ref(null)
    const loading = ref(false)
    
    const refresh = async () => {
      loading.value = true
      try {
        systemInfo.value = await systemService.getSystemInfo()
        emit('system-updated', systemInfo.value)
      } catch (error) {
        console.error('Failed to get system info:', error)
      } finally {
        loading.value = false
      }
    }
    
    const formatGpuMemory = (gpu) => {
      if (!gpu) return 'Unknown'
      const total = gpu.memory_total
      const free = gpu.memory_free
      if (total) {
        return `${total} MB (${free} MB free)`
      }
      return 'Unknown'
    }
    
    onMounted(() => {
      refresh()
    })
    
    return {
      systemInfo,
      loading,
      refresh,
      formatGpuMemory
    }
  }
}
</script>

<style scoped>
.system-info {
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.info-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
}

.info-header h3 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
}

.refresh-button {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-button:hover:not(:disabled) {
  background: #f9fafb;
  border-color: #d1d5db;
}

.refresh-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.info-card {
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 1rem;
}

.info-card.gpu-not-available {
  opacity: 0.7;
}

.info-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.75rem;
}

.info-content p {
  margin: 0.25rem 0;
  font-size: 0.875rem;
  color: #4b5563;
}

.info-content strong {
  color: #374151;
}

.no-info {
  text-align: center;
  padding: 3rem;
  color: #6b7280;
}

.no-info button {
  margin-top: 1rem;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: #3b82f6;
  color: white;
  border: none;
}

.btn-primary:hover {
  background: #2563eb;
}
</style>