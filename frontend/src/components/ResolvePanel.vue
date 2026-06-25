<template>
  <div class="panel">
    <h2 class="panel-title">Resolve Dependencies</h2>

    <div v-if="errorMessage" class="error-msg mb-4">{{ errorMessage }}</div>

    <div class="bg-white rounded-lg shadow-sm border p-4 mb-6">
      <h3 class="font-semibold mb-3">Add Packages</h3>
      <div class="flex gap-2 mb-3">
        <input v-model="newPackage.name" placeholder="Package name (e.g. tensorflow)"
               class="form-input flex-1" @keyup.enter="addPackage" />
        <select v-model="newPackage.ecosystem" class="form-select w-40">
          <option value="">Auto-detect</option>
          <option value="pypi">PyPI (Python)</option>
          <option value="npm">NPM (Node.js)</option>
          <option value="conda">Conda</option>
          <option value="maven">Maven (Java)</option>
          <option value="crates">Crates (Rust)</option>
        </select>
        <button @click="addPackage" class="btn btn-primary">Add</button>
      </div>

      <div v-if="packages.length > 0" class="space-y-1">
        <div v-for="(pkg, i) in packages" :key="i"
             class="flex justify-between items-center p-2 bg-gray-50 rounded text-sm">
          <span>{{ pkg.name }} <span v-if="pkg.ecosystem" class="text-gray-500">({{ pkg.ecosystem }})</span></span>
          <button @click="removePackage(i)" class="text-red-600 hover:text-red-800 text-sm">Remove</button>
        </div>
      </div>
    </div>

    <div class="text-center mb-6">
      <button @click="resolveDependencies" :disabled="packages.length === 0 || resolving"
              class="btn btn-primary btn-lg">
        {{ resolving ? 'Resolving...' : 'Resolve Dependencies' }}
      </button>
    </div>

    <div v-if="resolvedPackages" class="bg-white rounded-lg shadow-sm border p-4 mb-6">
      <h3 class="font-semibold mb-3">Resolved Dependencies</h3>

      <div class="space-y-1 mb-4">
        <div v-for="(info, name) in resolvedPackages.resolved_packages" :key="name"
             class="flex justify-between p-2 bg-gray-50 rounded text-sm">
          <div>
            <span>{{ name }}</span>
            <div v-if="info.system_requirements" class="text-xs text-gray-500 mt-1">
              <span>Python: {{ info.system_requirements.python_versions?.join(', ') || 'Any' }}</span>
              <span v-if="info.system_requirements.cuda_versions" class="ml-2">CUDA: {{ info.system_requirements.cuda_versions.join(', ') }}</span>
            </div>
          </div>
          <span class="text-gray-600">{{ info.version }} ({{ info.ecosystem }})</span>
        </div>
      </div>

      <div v-if="resolvedPackages.warnings?.length > 0" class="mb-4">
        <h4 class="font-semibold text-yellow-700 text-sm mb-1">Warnings</h4>
        <ul class="list-disc list-inside text-sm text-yellow-700">
          <li v-for="(w, i) in resolvedPackages.warnings" :key="i">{{ w }}</li>
        </ul>
      </div>

      <div v-if="exportFormats.length > 0">
        <h4 class="font-semibold mb-2 text-sm">Export</h4>
        <div class="flex flex-wrap gap-2">
          <button v-for="fmt in exportFormats" :key="typeof fmt === 'string' ? fmt : fmt.format"
                  @click="exportConfig(typeof fmt === 'string' ? fmt : fmt.format)" :disabled="exporting"
                  class="btn btn-secondary btn-sm">
            {{ typeof fmt === 'string' ? fmt : fmt.format }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="exportPreview" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div class="bg-white rounded-lg max-w-4xl w-full max-h-screen overflow-hidden">
        <div class="p-4 border-b flex justify-between items-center">
          <h3 class="font-semibold">{{ exportPreview.format }}</h3>
          <button @click="exportPreview = null" class="text-gray-500 hover:text-gray-700">&times;</button>
        </div>
        <div class="p-4 overflow-auto" style="max-height: 70vh;">
          <pre class="bg-gray-100 p-4 rounded overflow-x-auto text-sm">{{ exportPreview.content }}</pre>
        </div>
        <div class="p-4 border-t flex justify-end gap-2">
          <button @click="copyToClipboard" class="btn btn-secondary">Copy</button>
          <button @click="downloadFile" class="btn btn-primary">Download</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import packageService from '../services/packageService'

export default {
  name: 'ResolvePanel',
  setup() {
    const packages = ref([])
    const newPackage = ref({ name: '', ecosystem: '' })
    const resolving = ref(false)
    const exporting = ref(false)
    const resolvedPackages = ref(null)
    const exportFormats = ref([])
    const exportPreview = ref(null)
    const errorMessage = ref(null)
    const successMessage = ref(null)

    onMounted(async () => {
      try {
        const resp = await packageService.getExportFormats()
        exportFormats.value = resp.formats || resp.data || []
      } catch (e) {
        errorMessage.value = 'Failed to load export formats'
        console.error('Failed to load export formats:', e)
      }
    })

    function addPackage() {
      if (!newPackage.value.name) {
        errorMessage.value = 'Package name is required.'
        return
      }
      packages.value.push({
        name: newPackage.value.name,
        ecosystem: newPackage.value.ecosystem || null
      })
      newPackage.value.name = ''
      newPackage.value.ecosystem = ''
      errorMessage.value = null
    }

    function removePackage(index) {
      packages.value.splice(index, 1)
      resolvedPackages.value = null
      exportPreview.value = null
    }

    async function resolveDependencies() {
      if (packages.value.length === 0) {
        errorMessage.value = 'No packages selected.'
        return
      }
      resolving.value = true
      errorMessage.value = null
      try {
        const result = await packageService.resolveDependencies(packages.value, null, { preferCompatibility: true })
        resolvedPackages.value = result.data || result
      } catch (e) {
        errorMessage.value = 'Failed to resolve dependencies. ' + (e.response?.data?.message || e.message)
      }
      resolving.value = false
    }

    async function exportConfig(format) {
      if (!resolvedPackages.value) return
      exporting.value = true
      try {
        const response = await packageService.exportConfiguration(
          resolvedPackages.value, format, null,
          { pin_versions: true, include_index_url: true }
        )
        exportPreview.value = { format, content: response.content }
      } catch (e) {
        errorMessage.value = 'Export failed: ' + (e.response?.data?.message || e.message)
      }
      exporting.value = false
    }

    function copyToClipboard() {
      if (!exportPreview.value) return
      navigator.clipboard.writeText(exportPreview.value.content).catch(() => {})
      successMessage.value = 'Copied to clipboard!'
      setTimeout(() => { successMessage.value = null }, 2000)
    }

    function downloadFile() {
      if (!exportPreview.value) return
      const blob = new Blob([exportPreview.value.content], { type: 'text/plain' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = exportPreview.value.format
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    }

    return {
      packages, newPackage, resolving, exporting, resolvedPackages,
      exportFormats, exportPreview, errorMessage, successMessage,
      addPackage, removePackage, resolveDependencies, exportConfig,
      copyToClipboard, downloadFile,
    }
  }
}
</script>
