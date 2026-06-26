<template>
  <div class="panel">
    <h2 class="panel-title">System</h2>

    <div class="tabs mb-4">
      <button v-for="tab in tabs" :key="tab.key" @click="activeTab = tab.key"
              class="tab" :class="{ 'tab-active': activeTab === tab.key }">
        {{ tab.label }}
      </button>
    </div>

    <!-- System Info (reuse existing SystemInfo component) -->
    <div v-if="activeTab === 'info'" class="mb-6">
      <SystemInfo />
    </div>

    <!-- GPU Info -->
    <div v-if="activeTab === 'gpu'" class="space-y-4">
      <button @click="fetchGpuInfo" class="btn btn-primary" :disabled="gpuLoading">
        {{ gpuLoading ? 'Loading...' : 'Detect GPU' }}
      </button>
      <div v-if="gpuInfo" class="bg-gray-50 rounded-lg p-4 space-y-2">
        <p><strong>Available:</strong> {{ gpuInfo.available ? 'Yes' : 'No' }}</p>
        <div v-if="gpuInfo.available && gpuInfo.devices">
          <div v-for="(dev, i) in gpuInfo.devices" :key="i" class="border-t pt-2 mt-2">
            <p><strong>Device {{ i + 1 }}:</strong> {{ dev.name }}</p>
            <p class="text-sm">Memory: {{ dev.memory_total || '?' }} MB ({{ dev.memory_free || '?' }} MB free)</p>
          </div>
        </div>
        <p v-if="gpuInfo.cuda"><strong>CUDA:</strong> {{ gpuInfo.cuda }}</p>
        <p v-if="gpuInfo.cudnn"><strong>cuDNN:</strong> {{ gpuInfo.cudnn }}</p>
      </div>
    </div>

    <!-- Runtime -->
    <div v-if="activeTab === 'runtime'" class="space-y-4">
      <div class="flex gap-2">
        <select v-model="runtimeName" class="form-select w-40">
          <option value="python">Python</option>
          <option value="node">Node.js</option>
          <option value="java">Java</option>
          <option value="gcc">GCC</option>
          <option value="docker">Docker</option>
          <option value="rust">Rust</option>
          <option value="go">Go</option>
          <option value="julia">Julia</option>
          <option value="r">R</option>
          <option value="dotnet">.NET</option>
          <option value="ruby">Ruby</option>
          <option value="php">PHP</option>
          <option value="kotlin">Kotlin</option>
          <option value="scala">Scala</option>
        </select>
        <button @click="fetchRuntime" class="btn btn-primary" :disabled="rtLoading">
          {{ rtLoading ? 'Loading...' : 'Get Info' }}
        </button>
      </div>
      <div v-if="runtimeInfo" class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <p v-for="(val, key) in runtimeInfo" :key="key"><strong>{{ key }}:</strong> {{ val }}</p>
      </div>
    </div>

    <!-- Benchmarks -->
    <div v-if="activeTab === 'benchmarks'" class="space-y-4">
      <div class="flex gap-2">
        <button @click="runBenchmarks(false)" class="btn btn-primary" :disabled="benchLoading">
          {{ benchLoading ? 'Running...' : 'Quick Benchmarks' }}
        </button>
        <button @click="runBenchmarks(true)" class="btn btn-secondary" :disabled="benchLoading">
          Comprehensive
        </button>
      </div>
      <div v-if="benchResults" class="bg-gray-50 rounded-lg p-4 text-sm">
        <pre class="whitespace-pre-wrap">{{ JSON.stringify(benchResults, null, 2) }}</pre>
      </div>
    </div>

    <!-- Analyze Environment -->
    <div v-if="activeTab === 'analyze'" class="space-y-4">
      <div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
        <p class="mb-2 text-gray-600">Upload a requirements.txt, package.json, Cargo.toml, go.mod, or other manifest</p>
        <input type="file" @change="handleFileUpload" accept=".txt,.json,.yml,.yaml,.toml,.cfg,.ini,.lock,.rb,.php" class="block mx-auto" />
      </div>
      <div v-if="envAnalysis" class="bg-gray-50 rounded-lg p-4 text-sm">
        <pre class="whitespace-pre-wrap">{{ JSON.stringify(envAnalysis, null, 2) }}</pre>
      </div>
    </div>

    <!-- Compatibility Check -->
    <div v-if="activeTab === 'compat_check'" class="space-y-4">
      <div class="bg-white rounded-lg shadow-sm border p-4">
        <p class="text-sm text-gray-600 mb-3">Define system requirements to check against your machine.</p>
        <div class="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label class="text-xs text-gray-500 block mb-1">OS</label>
            <select v-model="compatReq.os" class="form-select w-full text-sm">
              <option value="">Any</option>
              <option value="linux">Linux</option>
              <option value="darwin">macOS</option>
              <option value="windows">Windows</option>
            </select>
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Min Memory (GB)</label>
            <input v-model.number="compatReq.memory" type="number" min="0" step="1" class="form-input w-full text-sm" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Min Python Version</label>
            <input v-model="compatReq.python" placeholder="e.g. 3.9" class="form-input w-full text-sm" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">CUDA Version</label>
            <input v-model="compatReq.cuda" placeholder="e.g. 11.8" class="form-input w-full text-sm" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Min GPU Memory (MB)</label>
            <input v-model.number="compatReq.gpuMemory" type="number" min="0" step="512" class="form-input w-full text-sm" />
          </div>
          <div>
            <label class="text-xs text-gray-500 block mb-1">Min Disk Space (GB)</label>
            <input v-model.number="compatReq.disk" type="number" min="0" step="1" class="form-input w-full text-sm" />
          </div>
        </div>
        <div class="flex gap-2">
          <button @click="checkSystemCompat" class="btn btn-primary" :disabled="ccLoading">
            {{ ccLoading ? 'Checking...' : 'Check System Compatibility' }}
          </button>
          <button @click="compatReq = { os: '', memory: 0, python: '', cuda: '', gpuMemory: 0, disk: 0 }" class="btn btn-secondary btn-sm">Reset</button>
        </div>
      </div>
      <div v-if="compatCheckResult" class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <div class="mb-2">
          <strong :class="compatCheckResult.compatible ? 'text-green-600' : 'text-red-600'">
            {{ compatCheckResult.compatible ? '✓ Compatible' : '✗ Not Compatible' }}
          </strong>
        </div>
        <div v-for="(check, i) in compatCheckResult.checks" :key="i" class="border-b pb-2">
          <span :class="check.status === 'pass' ? 'text-green-600' : 'text-red-600'">
            {{ check.status === 'pass' ? '✓' : '✗' }}
          </span>
          {{ check.message || check.type }}
        </div>
        <div v-if="compatCheckResult.errors?.length" class="text-red-600 mt-2">
          <div v-for="(e, i) in compatCheckResult.errors" :key="i">• {{ e }}</div>
        </div>
        <div v-if="compatCheckResult.warnings?.length" class="text-yellow-600 mt-2">
          <div v-for="(w, i) in compatCheckResult.warnings" :key="i">• {{ w }}</div>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-msg mt-4">{{ error }}</div>
  </div>
</template>

<script>
import { ref } from 'vue'
import SystemInfo from './SystemInfo.vue'
import systemService from '../services/systemService'

export default {
  name: 'SystemPanel',
  components: { SystemInfo },
  setup() {
    const tabs = [
      { key: 'info', label: 'System Info' },
      { key: 'gpu', label: 'GPU' },
      { key: 'runtime', label: 'Runtime' },
      { key: 'benchmarks', label: 'Benchmarks' },
      { key: 'analyze', label: 'Analyze Env' },
      { key: 'compat_check', label: 'Compat Check' },
    ]
    const activeTab = ref('info')
    const error = ref(null)

    // GPU
    const gpuInfo = ref(null)
    const gpuLoading = ref(false)
    async function fetchGpuInfo() {
      gpuLoading.value = true
      error.value = null
      try {
        const resp = await systemService.getGpuInfo()
        gpuInfo.value = resp.gpu || resp
      } catch (e) {
        error.value = 'GPU detection failed: ' + (e.response?.data?.message || e.message)
      }
      gpuLoading.value = false
    }

    // Runtime
    const runtimeName = ref('python')
    const runtimeInfo = ref(null)
    const rtLoading = ref(false)
    async function fetchRuntime() {
      rtLoading.value = true
      error.value = null
      try {
        const resp = await systemService.getRuntimeInfo(runtimeName.value)
        runtimeInfo.value = resp.info || resp
      } catch (e) {
        error.value = 'Runtime info failed: ' + (e.response?.data?.message || e.message)
      }
      rtLoading.value = false
    }

    // Benchmarks
    const benchResults = ref(null)
    const benchLoading = ref(false)
    async function runBenchmarks(comprehensive) {
      benchLoading.value = true
      error.value = null
      try {
        const resp = await systemService.runBenchmarks(comprehensive)
        benchResults.value = resp.benchmarks || resp
      } catch (e) {
        error.value = 'Benchmarks failed: ' + (e.response?.data?.message || e.message)
      }
      benchLoading.value = false
    }

    // Analyze environment
    const envAnalysis = ref(null)
    async function handleFileUpload(event) {
      const file = event.target.files?.[0]
      if (!file) return
      error.value = null
      try {
        const resp = await systemService.analyzeEnvironmentFile(file)
        envAnalysis.value = resp.analysis || resp
      } catch (e) {
        error.value = 'Analysis failed: ' + (e.response?.data?.message || e.message)
      }
    }

    // Compatibility check
    const compatCheckResult = ref(null)
    const ccLoading = ref(false)
    const compatReq = ref({ os: '', memory: 0, python: '', cuda: '', gpuMemory: 0, disk: 0 })
    async function checkSystemCompat() {
      ccLoading.value = true
      error.value = null
      try {
        const reqs = []
        if (compatReq.value.os) reqs.push({ type: 'os', minimum: { name: compatReq.value.os } })
        if (compatReq.value.memory > 0) reqs.push({ type: 'memory', minimum: { gb: compatReq.value.memory } })
        if (compatReq.value.python) reqs.push({ type: 'python', minimum: { version: compatReq.value.python } })
        if (compatReq.value.cuda) reqs.push({ type: 'gpu', minimum: { cuda: compatReq.value.cuda } })
        if (compatReq.value.gpuMemory > 0) reqs.push({ type: 'gpu', minimum: { memory_gb: compatReq.value.gpuMemory / 1024 } })
        if (compatReq.value.disk > 0) reqs.push({ type: 'disk', minimum: { gb: compatReq.value.disk } })
        const resp = await systemService.checkCompatibility(reqs)
        compatCheckResult.value = resp
      } catch (e) {
        error.value = 'Compatibility check failed: ' + (e.response?.data?.message || e.message)
      }
      ccLoading.value = false
    }

    return {
      tabs, activeTab, error,
      gpuInfo, gpuLoading, fetchGpuInfo,
      runtimeName, runtimeInfo, rtLoading, fetchRuntime,
      benchResults, benchLoading, runBenchmarks,
      envAnalysis, handleFileUpload,
      compatCheckResult, ccLoading, compatReq, checkSystemCompat,
    }
  }
}
</script>
