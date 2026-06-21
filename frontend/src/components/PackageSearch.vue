<template>
  <div class="package-search">
    <div class="bg-white rounded-lg shadow-md p-6 mb-6">
      <h2 class="text-xl font-semibold mb-4">Search Packages</h2>
      
      <div v-if="searchError" class="text-red-600 mb-4 error-message">
        {{ searchError }}
      </div>
      
      <div class="search-bar">
        <input
          v-model="searchQuery"
          @input="debouncedSearch"
          @keyup.enter="search"
          placeholder="Search packages..."
          class="search-input"
        />
        
        <select v-model="selectedEcosystem" class="ecosystem-select">
          <option value="">All Ecosystems</option>
          <option value="pypi">PyPI (Python)</option>
          <option value="npm">NPM (Node.js)</option>
          <option value="conda">Conda</option>
          <option value="maven">Maven (Java)</option>
          <option value="crates">Crates (Rust)</option>
        </select>
        
        <button @click="search" :disabled="searching" class="search-button">
          {{ searching ? 'Searching...' : 'Search' }}
        </button>
      </div>
      
      <div v-if="searchResults.length > 0" class="info-grid">
        <div 
          v-for="result in searchResults" 
          :key="`${result.ecosystem}-${result.name}`"
          class="info-card"
          @click="selectPackage(result)"
        >
          <div class="info-title">
            <span class="package-name">{{ result.name }}</span>
            <span class="package-ecosystem">{{ result.ecosystem }}</span>
          </div>
          <div class="info-content">
            <p class="package-description">{{ result.description || 'No description available' }}</p>
            <p class="package-version">Latest: {{ result.version || 'Unknown' }}</p>
            <div v-if="result.system_requirements" class="requirements">
              <p>Python: {{ result.system_requirements.python_versions?.join(', ') || 'Any' }}</p>
              <p v-if="result.system_requirements.cuda_versions">
                CUDA: {{ result.system_requirements.cuda_versions.join(', ') }}
              </p>
              <p v-if="result.system_requirements.node">
                Node: {{ result.system_requirements.node.version_spec || 'Any' }}
              </p>
            </div>
          </div>
        </div>
      </div>
      
      <div v-else-if="searched && !searching" class="no-results">
        No packages found matching "{{ lastSearchQuery }}"
      </div>
    </div>
  </div>
</template>

<script>
import { ref } from 'vue';
import { debounce } from 'lodash';
import packageService from '../services/packageService';

export default {
  name: 'PackageSearch',
  emits: ['package-selected'],
  setup(props, { emit }) {
    const searchQuery = ref('');
    const selectedEcosystem = ref('');
    const searching = ref(false);
    const searched = ref(false);
    const searchResults = ref([]);
    const lastSearchQuery = ref('');
    const searchError = ref(null);
    
    const search = async () => {
      if (!searchQuery.value.trim()) {
        searchError.value = 'Please enter a package name.';
        return;
      }
      
      searching.value = true;
      searched.value = true;
      lastSearchQuery.value = searchQuery.value;
      
      try {
        const results = await packageService.searchPackages(
          searchQuery.value,
          selectedEcosystem.value ? [selectedEcosystem.value] : null
          { flatten: true }
        );
        searchResults.value = results;
        searchError.value = null;
      } catch (error) {
        console.error('Search failed:', error);
        searchResults.value = [];
        searchError.value = 'Failed to search packages. Please try again.';
      } finally {
        searching.value = false;
      }
    };
    
    const debouncedSearch = debounce(search, 300);
    
    const selectPackage = (packageInfo) => {
      emit('package-selected', packageInfo);
      searchQuery.value = '';
      searchResults.value = [];
      searched.value = false;
      searchError.value = null;
    };
    
    return {
      searchQuery,
      selectedEcosystem,
      searching,
      searched,
      searchResults,
      lastSearchQuery,
      searchError,
      search,
      debouncedSearch,
      selectPackage
    };
  }
};
</script>

<style scoped>
.package-search {
  margin-bottom: 1rem;
}

.search-bar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.search-input {
  flex: 1;
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 1rem;
}

.ecosystem-select {
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
}

.search-button {
  padding: 0.5rem 1rem;
  background: #3b82f6;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}

.search-button:hover:not(:disabled) {
  background: #2563eb;
}

.search-button:disabled {
  background: #9ca3af;
  cursor: not-allowed;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.info-card {
  padding: 1rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}

.info-card:hover {
  background: #f3f4f6;
}

.info-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
}

.package-name {
  font-weight: 600;
  color: #1f2937;
}

.package-ecosystem {
  font-size: 0.875rem;
  padding: 0.125rem 0.5rem;
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 4px;
}

.info-content p {
  margin: 0.25rem 0;
  font-size: 0.875rem;
  color: #4b5563;
}

.package-description {
  font-size: 0.875rem;
  color: #4b5563;
  margin-bottom: 0.25rem;
}

.package-version {
  font-size: 0.75rem;
  color: #6b7280;
}

.requirements {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: #4b5563;
}

.no-results {
  text-align: center;
  padding: 2rem;
  color: #6b7280;
}

.error-message {
  animation: fadeIn 0.5s;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>