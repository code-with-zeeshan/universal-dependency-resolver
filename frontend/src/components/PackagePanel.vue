<template>
  <div class="panel">
    <h2 class="panel-title">Packages</h2>

    <div class="tabs mb-4">
      <button v-for="tab in tabs" :key="tab.key" @click="activeTab = tab.key"
              class="tab" :class="{ 'tab-active': activeTab === tab.key }">
        {{ tab.label }}
      </button>
    </div>

    <!-- Search -->
    <div v-if="activeTab === 'search'" class="space-y-4">
      <div class="flex gap-2">
        <input v-model="searchQuery" placeholder="Search packages (e.g. flask, numpy)"
               class="form-input flex-1" @keyup.enter="doSearch" />
        <select v-model="searchEcosystem" class="form-select w-40">
          <option value="">All ecosystems</option>
          <option value="pypi">PyPI</option>
          <option value="npm">NPM</option>
          <option value="conda">Conda</option>
          <option value="maven">Maven</option>
          <option value="crates">Crates</option>
        </select>
        <button @click="doSearch" class="btn btn-primary" :disabled="searching">
          {{ searching ? 'Searching...' : 'Search' }}
        </button>
      </div>
      <div v-if="searchResults" class="space-y-2">
        <div v-for="(pkgs, eco) in searchResults.results" :key="eco">
          <h3 class="font-semibold text-sm text-gray-600 mt-3 mb-1">{{ eco }}</h3>
          <div v-for="pkg in pkgs" :key="pkg.name"
               class="flex justify-between p-2 bg-gray-50 rounded hover:bg-gray-100 cursor-pointer"
               @click="showPackageInfo(eco, pkg.name)">
            <span>{{ pkg.name }}</span>
            <span class="text-sm text-gray-500">{{ pkg.version }}</span>
          </div>
        </div>
        <p v-if="!hasResults" class="text-gray-500 text-sm">No results found.</p>
      </div>
    </div>

    <!-- Info -->
    <div v-if="activeTab === 'info'" class="space-y-4">
      <div class="flex gap-2">
        <select v-model="infoEcosystem" class="form-select w-32">
          <option value="pypi">PyPI</option>
          <option value="npm">NPM</option>
          <option value="conda">Conda</option>
        </select>
        <input v-model="infoPackage" placeholder="Package name" class="form-input flex-1" @keyup.enter="fetchInfo" />
        <button @click="fetchInfo" class="btn btn-primary" :disabled="infoLoading">{{ infoLoading ? 'Loading...' : 'Get Info' }}</button>
      </div>
      <div v-if="packageInfo" class="bg-gray-50 rounded-lg p-4 space-y-2">
        <p><strong>Name:</strong> {{ packageInfo.name }}</p>
        <p><strong>Version:</strong> {{ packageInfo.version }}</p>
        <p><strong>Ecosystem:</strong> {{ packageInfo.ecosystem }}</p>
        <p v-if="packageInfo.description"><strong>Description:</strong> {{ packageInfo.description }}</p>
        <p v-if="packageInfo.license"><strong>License:</strong> {{ packageInfo.license }}</p>
        <p v-if="packageInfo.homepage"><strong>Homepage:</strong> <a :href="packageInfo.homepage" target="_blank" class="text-blue-600">{{ packageInfo.homepage }}</a></p>
      </div>
      <div v-if="infoError" class="error-msg">{{ infoError }}</div>
    </div>

    <!-- Versions -->
    <div v-if="activeTab === 'versions'" class="space-y-4">
      <div class="flex gap-2">
        <select v-model="verEcosystem" class="form-select w-32">
          <option value="pypi">PyPI</option>
          <option value="npm">NPM</option>
        </select>
        <input v-model="verPackage" placeholder="Package name" class="form-input flex-1" @keyup.enter="fetchVersions" />
        <button @click="fetchVersions" class="btn btn-primary" :disabled="verLoading">{{ verLoading ? 'Loading...' : 'List Versions' }}</button>
      </div>
      <div v-if="versions" class="space-y-1">
        <div v-for="v in versions" :key="v.version"
             class="p-2 bg-gray-50 rounded text-sm">{{ v.version }} <span class="text-gray-500" v-if="v.release_date">{{ v.release_date }}</span></div>
      </div>
    </div>

    <!-- Dependencies -->
    <div v-if="activeTab === 'deps'" class="space-y-4">
      <div class="flex gap-2">
        <select v-model="depEcosystem" class="form-select w-32">
          <option value="pypi">PyPI</option>
          <option value="npm">NPM</option>
        </select>
        <input v-model="depPackage" placeholder="Package name" class="form-input flex-1" @keyup.enter="fetchDeps" />
        <button @click="fetchDeps" class="btn btn-primary" :disabled="depLoading">{{ depLoading ? 'Loading...' : 'Get Dependencies' }}</button>
      </div>
      <div v-if="dependencies" class="space-y-1">
        <div v-for="(dep, name) in dependencies" :key="name"
             class="flex justify-between p-2 bg-gray-50 rounded text-sm">
          <span>{{ name }}</span>
          <span class="text-gray-500">{{ dep }}</span>
        </div>
      </div>
    </div>

    <!-- Compatibility -->
    <div v-if="activeTab === 'compat'" class="space-y-4">
      <div class="flex gap-2">
        <select v-model="compEcosystem" class="form-select w-32">
          <option value="pypi">PyPI</option>
          <option value="npm">NPM</option>
        </select>
        <input v-model="compPackage" placeholder="Package name" class="form-input flex-1" @keyup.enter="fetchCompat" />
        <button @click="fetchCompat" class="btn btn-primary" :disabled="compLoading">{{ compLoading ? 'Loading...' : 'Check' }}</button>
      </div>
      <div v-if="compatibility" class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <p v-for="(val, key) in compatibility" :key="key"><strong>{{ key }}:</strong> {{ typeof val === 'object' ? JSON.stringify(val) : val }}</p>
      </div>
    </div>

    <!-- Compare -->
    <div v-if="activeTab === 'compare'" class="space-y-4">
      <div class="flex gap-2">
        <input v-model="compareInput" placeholder="Package names, comma-separated (e.g. flask, django)"
               class="form-input flex-1" @keyup.enter="doCompare" />
        <button @click="doCompare" class="btn btn-primary" :disabled="compLoading">{{ compLoading ? 'Loading...' : 'Compare' }}</button>
      </div>
      <div v-if="compareResult" class="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
        <pre class="whitespace-pre-wrap">{{ JSON.stringify(compareResult, null, 2) }}</pre>
      </div>
    </div>

    <div v-if="error" class="error-msg mt-4">{{ error }}</div>
  </div>
</template>

<script>
import { ref, computed } from 'vue'
import packageService from '../services/packageService'

export default {
  name: 'PackagePanel',
  setup() {
    const tabs = [
      { key: 'search', label: 'Search' },
      { key: 'info', label: 'Info' },
      { key: 'versions', label: 'Versions' },
      { key: 'deps', label: 'Dependencies' },
      { key: 'compat', label: 'Compatibility' },
      { key: 'compare', label: 'Compare' },
    ]
    const activeTab = ref('search')
    const error = ref(null)

    // Search
    const searchQuery = ref('')
    const searchEcosystem = ref('')
    const searchResults = ref(null)
    const searching = ref(false)

    async function doSearch() {
      if (!searchQuery.value) return
      searching.value = true
      error.value = null
      try {
        const ecosystems = searchEcosystem.value ? [searchEcosystem.value] : null
        searchResults.value = await packageService.searchPackages(searchQuery.value, ecosystems)
      } catch (e) {
        error.value = 'Search failed: ' + (e.response?.data?.message || e.message)
      }
      searching.value = false
    }

    const hasResults = computed(() => searchResults.value && Object.values(searchResults.value.results || {}).some(a => a.length > 0))

    // Info
    const infoEcosystem = ref('pypi')
    const infoPackage = ref('')
    const packageInfo = ref(null)
    const infoLoading = ref(false)
    const infoError = ref(null)

    async function fetchInfo() {
      if (!infoPackage.value) return
      infoLoading.value = true
      infoError.value = null
      packageInfo.value = null
      try {
        const resp = await packageService.getPackageInfo(infoEcosystem.value, infoPackage.value)
        packageInfo.value = resp.data || resp
      } catch (e) {
        infoError.value = 'Failed: ' + (e.response?.data?.message || e.message)
      }
      infoLoading.value = false
    }

    function showPackageInfo(eco, name) {
      infoEcosystem.value = eco
      infoPackage.value = name
      activeTab.value = 'info'
      fetchInfo()
    }

    // Versions
    const verEcosystem = ref('pypi')
    const verPackage = ref('')
    const versions = ref(null)
    const verLoading = ref(false)

    async function fetchVersions() {
      if (!verPackage.value) return
      verLoading.value = true
      try {
        const resp = await packageService.getPackageVersions(verEcosystem.value, verPackage.value)
        versions.value = resp.versions || resp.data || resp
      } catch (e) {
        error.value = 'Failed: ' + (e.response?.data?.message || e.message)
      }
      verLoading.value = false
    }

    // Dependencies
    const depEcosystem = ref('pypi')
    const depPackage = ref('')
    const dependencies = ref(null)
    const depLoading = ref(false)

    async function fetchDeps() {
      if (!depPackage.value) return
      depLoading.value = true
      try {
        const resp = await packageService.getPackageDependencies(depEcosystem.value, depPackage.value)
        dependencies.value = resp.dependencies || resp.data || resp
      } catch (e) {
        error.value = 'Failed: ' + (e.response?.data?.message || e.message)
      }
      depLoading.value = false
    }

    // Compatibility
    const compEcosystem = ref('pypi')
    const compPackage = ref('')
    const compatibility = ref(null)
    const compLoading = ref(false)

    async function fetchCompat() {
      if (!compPackage.value) return
      compLoading.value = true
      try {
        const resp = await packageService.getPackageCompatibility(compEcosystem.value, compPackage.value)
        compatibility.value = resp.compatibility || resp.data || resp
      } catch (e) {
        error.value = 'Failed: ' + (e.response?.data?.message || e.message)
      }
      compLoading.value = false
    }

    // Compare
    const compareInput = ref('')
    const compareResult = ref(null)

    async function doCompare() {
      if (!compareInput.value) return
      compLoading.value = true
      try {
        const names = compareInput.value.split(',').map(s => s.trim()).filter(Boolean)
        compareResult.value = await packageService.comparePackages(names)
      } catch (e) {
        error.value = 'Failed: ' + (e.response?.data?.message || e.message)
      }
      compLoading.value = false
    }

    return {
      tabs, activeTab, error,
      searchQuery, searchEcosystem, searchResults, searching, doSearch, hasResults,
      infoEcosystem, infoPackage, packageInfo, infoLoading, infoError, fetchInfo, showPackageInfo,
      verEcosystem, verPackage, versions, verLoading, fetchVersions,
      depEcosystem, depPackage, dependencies, depLoading, fetchDeps,
      compEcosystem, compPackage, compatibility, compLoading, fetchCompat,
      compareInput, compareResult, doCompare,
    }
  }
}
</script>
