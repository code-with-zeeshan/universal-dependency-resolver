<template>
  <div id="app">
    <div class="container mx-auto p-4">
      <h1 class="text-3xl font-bold mb-8 text-center">
        Universal Dependency Resolver
      </h1>
      
      <div v-if="errorMessage" class="text-red-600 text-center mb-6 error-message">
        {{ errorMessage }}
      </div>
      
      <!-- System Info Section -->
      <SystemInfo @system-updated="updateSystemInfo" />
      
      <!-- Package Input Section -->
      <div class="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 class="text-xl font-semibold mb-4">Add Packages</h2>
        
        <div class="flex gap-4 mb-4">
          <input
            v-model="newPackage.name"
            placeholder="Package name (e.g., tensorflow, tensorrt)"
            class="form-input flex-1"
            @keyup.enter="addPackage"
          />
          
          <select v-model="newPackage.ecosystem" class="form-select">
            <option value="">Auto-detect</option>
            <option value="pypi">PyPI (Python)</option>
            <option value="npm">NPM (Node.js)</option>
            <option value="conda">Conda</option>
            <option value="maven">Maven (Java)</option>
            <option value="crates">Crates (Rust)</option>
          </select>
          
          <button @click="addPackage" class="btn btn-primary">
            Add Package
          </button>
        </div>
        
        <!-- Package List -->
        <div v-if="packages.length > 0" class="space-y-2">
          <div 
            v-for="(pkg, index) in packages" 
            :key="index"
            class="flex items-center justify-between p-3 bg-gray-50 rounded"
          >
            <span>
              {{ pkg.name }}
              <span v-if="pkg.ecosystem" class="text-sm text-gray-600">
                ({{ pkg.ecosystem }})
              </span>
            </span>
            <button 
              @click="removePackage(index)"
              class="text-red-600 hover:text-red-800"
            >
              Remove
            </button>
          </div>
        </div>
      </div>
      
      <!-- Resolve Button -->
      <div class="text-center mb-6">
        <button 
          @click="resolveDependencies"
          :disabled="packages.length === 0 || resolving"
          class="btn btn-primary btn-lg"
        >
          {{ resolving ? 'Resolving...' : 'Resolve Dependencies' }}
        </button>
      </div>
      
      <!-- Results Section -->
      <div v-if="resolvedPackages" class="bg-white rounded-lg shadow-md p-6 mb-6">
        <h2 class="text-xl font-semibold mb-4">Resolved Dependencies</h2>
        
        <!-- Resolved Packages -->
        <div class="mb-6">
          <h3 class="font-semibold mb-2">Packages</h3>
          <div class="space-y-1">
            <div 
              v-for="(info, name) in resolvedPackages.resolved_packages" 
              :key="name"
              class="flex justify-between p-2 bg-gray-50 rounded"
            >
              <div>
                <span>{{ name }}</span>
                <div v-if="info.system_requirements" class="text-sm text-gray-600 mt-1">
                  <span>Python: {{ info.system_requirements.python_versions?.join(', ') || 'Any' }}</span>
                  <span v-if="info.system_requirements.cuda_versions" class="ml-2">
                    CUDA: {{ info.system_requirements.cuda_versions.join(', ') }}
                  </span>
                  <span v-if="info.system_requirements.node" class="ml-2">
                    Node: {{ info.system_requirements.node.version_spec || 'Any' }}
                  </span>
                </div>
              </div>
              <span class="text-sm text-gray-600">
                {{ info.version }} ({{ info.ecosystem }})
              </span>
            </div>
          </div>
        </div>
        
        <!-- Warnings -->
        <div v-if="resolvedPackages.warnings?.length > 0" class="mb-6">
          <h3 class="font-semibold mb-2 text-yellow-600">Warnings</h3>
          <ul class="list-disc list-inside">
            <li v-for="(warning, index) in resolvedPackages.warnings" :key="index">
              {{ warning }}
            </li>
          </ul>
        </div>
        
        <!-- Export Options -->
        <div>
          <h3 class="font-semibold mb-4">Export Configuration</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
            <button 
              v-for="format in exportFormats" 
              :key="format"
              @click="exportConfig(format)"
              :disabled="exporting"
              class="btn btn-secondary btn-sm"
            >
              {{ format }}
            </button>
          </div>
        </div>
      </div>
      
      <!-- Export Preview Modal -->
      <div v-if="exportPreview" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4">
        <div class="bg-white rounded-lg max-w-4xl w-full max-h-screen overflow-hidden">
          <div class="p-4 border-b flex justify-between items-center">
            <h3 class="text-lg font-semibold">{{ exportPreview.format }}</h3>
            <button @click="exportPreview = null" class="text-gray-500 hover:text-gray-700">
              ✕
            </button>
          </div>
          
          <div class="p-4 overflow-auto" style="max-height: 70vh;">
            <pre class="bg-gray-100 p-4 rounded overflow-x-auto">{{ exportPreview.content }}</pre>
          </div>
          
          <div class="p-4 border-t flex justify-end gap-2">
            <button @click="copyToClipboard" class="btn btn-secondary">
              Copy to Clipboard
            </button>
            <button @click="downloadFile" class="btn btn-primary">
              Download
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import SystemInfo from './components/SystemInfo.vue';
import systemService from './services/systemService';
import packageService from './services/packageService';

export default {
  name: 'App',
  components: { SystemInfo },
  data() {
    return {
      systemInfo: null,
      scanning: false,
      packages: [],
      newPackage: {
        name: '',
        ecosystem: ''
      },
      resolving: false,
      exporting: false,
      resolvedPackages: null,
      exportFormats: [],
      exportPreview: null,
      errorMessage: null
    };
  },
  async mounted() {
    try {
      this.exportFormats = await packageService.getExportFormats();
      this.errorMessage = null;
    } catch (error) {
      console.error('Failed to load export formats:', error);
      this.errorMessage = 'Failed to load export formats. Please try again.';
    }
  },
  methods: {
    updateSystemInfo(systemInfo) {
      this.systemInfo = systemInfo;
      this.errorMessage = null;
    },
    async scanSystem() {
      this.scanning = true;
      try {
        this.systemInfo = await systemService.getSystemInfo();
        this.errorMessage = null;
      } catch (error) {
        console.error('System scan failed:', error);
        this.errorMessage = 'Failed to scan system. Please try again.';
      } finally {
        this.scanning = false;
      }
    },
    addPackage() {
      if (this.newPackage.name) {
        this.packages.push({
          name: this.newPackage.name,
          ecosystem: this.newPackage.ecosystem || null
        });
        this.newPackage.name = '';
        this.newPackage.ecosystem = '';
        this.errorMessage = null;
      } else {
        this.errorMessage = 'Package name is required.';
      }
    },
    removePackage(index) {
      this.packages.splice(index, 1);
      this.resolvedPackages = null;
      this.exportPreview = null;
      this.errorMessage = null;
    },
    async resolveDependencies() {
      if (this.packages.length === 0) {
        this.errorMessage = 'No packages selected.';
        return;
      }
      this.resolving = true;
      try {
        this.resolvedPackages = await packageService.resolveDependencies(
          this.packages,
          this.systemInfo,
          { preferCompatibility: true }
        );
        this.errorMessage = null;
      } catch (error) {
        console.error('Dependency resolution failed:', error);
        this.errorMessage = 'Failed to resolve dependencies. Please try again.';
      } finally {
        this.resolving = false;
      }
    },
    async exportConfig(format) {
      if (!this.resolvedPackages) {
        this.errorMessage = 'No resolved packages to export.';
        return;
      }
      this.exporting = true;
      try {
        const response = await packageService.exportConfiguration(
          this.resolvedPackages,
          format,
          this.systemInfo,
          { pin_versions: true, include_index_url: true }
        );
        this.exportPreview = { format: format, content: response.content };
        this.errorMessage = null;
      } catch (error) {
        console.error('Export failed:', error);
        this.errorMessage = `Failed to export as ${format}. Please try again.`;
      } finally {
        this.exporting = false;
      }
    },
    copyToClipboard() {
      if (!this.exportPreview) return;
      navigator.clipboard.writeText(this.exportPreview.content)
        .then(() => {
          this.errorMessage = 'Copied to clipboard!';
          setTimeout(() => { this.errorMessage = null; }, 2000);
        })
        .catch(err => {
          console.error('Failed to copy:', err);
          this.errorMessage = 'Failed to copy to clipboard.';
        });
    },
    downloadFile() {
      if (!this.exportPreview) return;
      const blob = new Blob([this.exportPreview.content], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = this.exportPreview.format;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    }
  }
};
</script>

<style>
@import 'tailwindcss/base';
@import 'tailwindcss/components';
@import 'tailwindcss/utilities';

.btn {
  @apply px-4 py-2 rounded font-medium transition-colors duration-200;
}

.btn-primary {
  @apply bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed;
}

.btn-secondary {
  @apply bg-gray-200 text-gray-800 hover:bg-gray-300;
}

.btn-sm {
  @apply px-3 py-1 text-sm;
}

.btn-lg {
  @apply px-6 py-3 text-lg;
}

.form-input {
  @apply px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500;
}

.form-select {
  @apply px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white;
}

.error-message {
  animation: fadeIn 0.5s;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>