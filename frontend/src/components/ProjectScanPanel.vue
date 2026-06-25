<template>
  <div class="panel">
    <h2 class="panel-title">Project Scan</h2>
    <p class="text-gray-600 mb-4 text-sm">
      Scan an entire project to detect manifests, resolve dependencies, and check system compatibility.
    </p>

    <div class="tabs mb-4">
      <button v-for="tab in tabs" :key="tab.id"
              class="tab" :class="{ active: activeTab === tab.id }"
              @click="activeTab = tab.id">
        {{ tab.label }}
      </button>
    </div>

    <!-- GitHub URL -->
    <div v-if="activeTab === 'github'" class="bg-white rounded-lg shadow-sm border p-4 mb-4">
      <h3 class="font-semibold mb-2">Scan from GitHub</h3>
      <p class="text-xs text-gray-500 mb-3">Paste a public GitHub repository URL. We'll clone it and scan all manifests.</p>
      <div class="flex gap-2">
        <input v-model="githubUrl" placeholder="https://github.com/owner/repo"
               class="form-input flex-1" @keyup.enter="startScan('github')" />
        <button @click="startScan('github')" :disabled="scanning || !githubUrl"
                class="btn btn-primary whitespace-nowrap">
          {{ scanning ? 'Scanning...' : 'Scan' }}
        </button>
      </div>
    </div>

    <!-- Upload Archive -->
    <div v-if="activeTab === 'upload'" class="bg-white rounded-lg shadow-sm border p-4 mb-4">
      <h3 class="font-semibold mb-2">Upload Project Archive</h3>
      <p class="text-xs text-gray-500 mb-3">Upload a <code>.zip</code> file of your project. We'll extract it and scan all manifests.</p>
      <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center">
        <input ref="fileInput" type="file" accept=".zip" class="hidden" @change="onFileSelected" />
        <div v-if="!selectedFile">
          <p class="text-gray-500 mb-2">Drag & drop a .zip file here, or</p>
          <button @click="$refs.fileInput.click()" class="btn btn-secondary">Browse Files</button>
        </div>
        <div v-else>
          <p class="text-sm mb-2">Selected: <strong>{{ selectedFile.name }}</strong> ({{ (selectedFile.size / 1024).toFixed(1) }} KB)</p>
          <button @click="startScan('upload')" :disabled="scanning" class="btn btn-primary">
            {{ scanning ? 'Scanning...' : 'Upload & Scan' }}
          </button>
          <button @click="selectedFile = null" class="btn btn-secondary ml-2">Change</button>
        </div>
      </div>
    </div>

    <!-- Local Path -->
    <div v-if="activeTab === 'local'" class="bg-white rounded-lg shadow-sm border p-4 mb-4">
      <h3 class="font-semibold mb-2">Scan Local Directory</h3>
      <p class="text-xs text-gray-500 mb-3">
        Point to a directory on the server. Only works when the backend runs on your machine
        (not via Docker or remote host).
      </p>
      <div class="flex gap-2">
        <input v-model="localPath" placeholder="/path/to/project"
               class="form-input flex-1" @keyup.enter="startScan('local')" />
        <button @click="startScan('local')" :disabled="scanning || !localPath"
                class="btn btn-primary whitespace-nowrap">
          {{ scanning ? 'Scanning...' : 'Scan' }}
        </button>
      </div>
    </div>

    <!-- Results -->
    <div v-if="result" class="space-y-4">
      <div class="bg-white rounded-lg shadow-sm border p-4">
        <div class="flex justify-between items-center mb-3">
          <h3 class="font-semibold">Scan Results</h3>
          <div class="flex gap-2">
            <button v-if="result.manifests && result.manifests.length > 0 && exportFormats.length > 0"
                    @click="showExport = true" class="btn btn-secondary btn-sm">Export</button>
            <button @click="clearResults" class="btn btn-secondary btn-sm">Clear</button>
          </div>
        </div>

        <!-- Source info -->
        <div class="text-xs text-gray-500 mb-3">
          Source: <strong>{{ result.source }}</strong>
          <span v-if="result.repo_url"> — {{ result.repo_url }}</span>
          <span v-if="result.directory_path"> — {{ result.directory_path }}</span>
          <span v-if="result.filename"> — {{ result.filename }}</span>
        </div>

        <!-- Status -->
        <div v-if="result.status === 'no_manifests'" class="bg-yellow-50 border border-yellow-200 text-yellow-800 p-3 rounded text-sm">
          No dependency manifests found in this project.
        </div>
        <div v-else-if="result.status === 'no_packages'" class="bg-yellow-50 border border-yellow-200 text-yellow-800 p-3 rounded text-sm">
          Manifests found but no packages could be parsed.
        </div>
        <div v-else-if="result.status === 'success'" class="space-y-3">
          <!-- System info -->
          <div class="bg-gray-50 rounded p-3 text-sm">
            <strong class="block mb-1">System</strong>
            <span class="text-gray-600">{{ result.system.os }} | {{ result.system.cpu }} | Python {{ result.system.python }}</span>
            <span v-if="result.system.gpu" class="ml-2">| GPU: {{ result.system.gpu }}
              <span v-if="result.system.cuda">(CUDA {{ result.system.cuda }})</span>
            </span>
          </div>

          <!-- Manifests -->
          <div v-if="result.manifests && result.manifests.length > 0">
            <strong class="block mb-1 text-sm">Manifests ({{ result.manifests.length }})</strong>
            <div class="flex flex-wrap gap-1">
              <span v-for="m in result.manifests" :key="m.filename"
                    class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs border border-blue-200">
                [{{ m.ecosystem }}] {{ m.filename }}
              </span>
            </div>
          </div>

          <!-- Packages -->
          <div v-if="result.packages && result.packages.length > 0">
            <strong class="block mb-1 text-sm">Packages ({{ result.packages.length }})</strong>
            <div class="overflow-x-auto">
              <table class="w-full text-sm">
                <thead>
                  <tr class="bg-gray-50">
                    <th class="text-left p-2 border-b">Name</th>
                    <th class="text-left p-2 border-b">Ecosystem</th>
                    <th class="text-left p-2 border-b">Constraint</th>
                    <th class="text-left p-2 border-b">Resolved</th>
                    <th class="text-left p-2 border-b">CUDA</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in result.packages" :key="p.name + p.ecosystem"
                      class="hover:bg-gray-50"
                      :class="{ 'text-gray-400': !p.resolved_version }">
                    <td class="p-2 border-b font-medium">{{ p.name }}</td>
                    <td class="p-2 border-b">{{ p.ecosystem }}</td>
                    <td class="p-2 border-b font-mono">{{ p.constraint || '*' }}</td>
                    <td class="p-2 border-b font-mono">{{ p.resolved_version || '—' }}</td>
                    <td class="p-2 border-b">{{ p.cuda_variant ? `cu${p.cuda_version}` : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- Warnings -->
          <div v-if="result.resolution && result.resolution.warnings && result.resolution.warnings.length > 0">
            <strong class="block mb-1 text-sm text-yellow-700">Warnings</strong>
            <ul class="list-disc list-inside text-xs text-yellow-700">
              <li v-for="(w, i) in result.resolution.warnings" :key="i">{{ w }}</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Export modal -->
      <div v-if="showExport" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
        <div class="bg-white rounded-lg max-w-lg w-full p-6">
          <h3 class="font-semibold mb-3">Export Resolved Dependencies</h3>
          <div class="flex flex-wrap gap-2 mb-4">
            <button v-for="fmt in exportFormats" :key="fmt.format || fmt"
                    @click="doExport(fmt.format || fmt)" :disabled="exporting"
                    class="btn btn-secondary btn-sm">
              {{ fmt.format || fmt }}
            </button>
          </div>
          <div v-if="exportPreview" class="mb-3">
            <pre class="bg-gray-100 p-3 rounded text-xs overflow-x-auto max-h-48">{{ exportPreview }}</pre>
          </div>
          <div class="flex justify-end gap-2">
            <button @click="showExport = false" class="btn btn-secondary">Close</button>
            <button v-if="exportPreview" @click="copyExport" class="btn btn-secondary">Copy</button>
            <button v-if="exportPreview" @click="downloadExport" class="btn btn-primary">Download</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Error -->
    <div v-if="error" class="bg-red-50 border border-red-200 text-red-700 p-3 rounded text-sm mt-4">
      {{ error }}
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import scanService from '../services/scanService'
import packageService from '../services/packageService'

export default {
  name: 'ProjectScanPanel',
  setup() {
    const tabs = [
      { id: 'github', label: 'GitHub URL' },
      { id: 'upload', label: 'Upload Archive' },
      { id: 'local', label: 'Local Path' },
    ]
    const activeTab = ref('github')
    const githubUrl = ref('')
    const localPath = ref('')
    const selectedFile = ref(null)
    const scanning = ref(false)
    const error = ref(null)
    const result = ref(null)
    const showExport = ref(false)
    const exportFormats = ref([])
    const exportPreview = ref(null)
    const exporting = ref(false)

    onMounted(async () => {
      try {
        const resp = await packageService.getExportFormats()
        exportFormats.value = resp.formats || resp.data || []
      } catch (e) {
        // Silent
      }
    })

    function onFileSelected(e) {
      selectedFile.value = e.target.files[0] || null
    }

    async function startScan(mode) {
      scanning.value = true
      error.value = null
      result.value = null
      try {
        let data
        if (mode === 'github') {
          data = await scanService.scanGithub(githubUrl.value)
        } else if (mode === 'upload') {
          if (!selectedFile.value) return
          data = await scanService.scanUpload(selectedFile.value)
        } else if (mode === 'local') {
          data = await scanService.scanLocal(localPath.value)
        }
        result.value = data
      } catch (e) {
        error.value = e.response?.data?.detail || e.message || 'Scan failed'
      }
      scanning.value = false
    }

    function clearResults() {
      result.value = null
      error.value = null
      exportPreview.value = null
      showExport.value = false
    }

    async function doExport(format) {
      if (!result.value?.resolution?.resolved_packages) return
      exporting.value = true
      exportPreview.value = null
      try {
        const pkgs = result.value.resolution.resolved_packages
        const resp = await packageService.exportConfiguration(
          pkgs, format, null,
          { pin_versions: true, include_index_url: true }
        )
        exportPreview.value = resp.content
      } catch (e) {
        error.value = 'Export failed: ' + (e.response?.data?.message || e.message)
      }
      exporting.value = false
    }

    function copyExport() {
      if (!exportPreview.value) return
      navigator.clipboard.writeText(exportPreview.value).catch(() => {})
    }

    function downloadExport() {
      if (!exportPreview.value) return
      const blob = new Blob([exportPreview.value], { type: 'text/plain' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'udr-export'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    }

    return {
      tabs, activeTab, githubUrl, localPath, selectedFile,
      scanning, error, result, showExport, exportFormats, exportPreview, exporting,
      onFileSelected, startScan, clearResults, doExport, copyExport, downloadExport,
    }
  }
}
</script>
