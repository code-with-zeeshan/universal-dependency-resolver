<!-- frontend/src/components/PackageCard.vue -->
<template>
  <div 
    :class="[
      'package-card',
      { 'selected': selected, 'loading': loading }
    ]"
    @click="handleClick"
  >
    <!-- Loading Overlay -->
    <div v-if="loading" class="loading-overlay">
      <LoadingSpinner size="small" />
    </div>

    <!-- Card Header -->
    <div class="card-header">
      <!-- Package Info -->
      <div class="package-info">
        <h3 class="package-name">
          {{ package.name }}
          <span v-if="package.ecosystem" class="ecosystem-badge">
            {{ ecosystemDisplay }}
          </span>
        </h3>
        
        <p v-if="package.description" class="package-description">
          {{ truncatedDescription }}
        </p>
      </div>

      <!-- Actions -->
      <div class="card-actions">
        <button 
          v-if="showFavorite"
          :class="['action-btn', { 'favorited': isFavorited }]"
          @click.stop="toggleFavorite"
          :title="isFavorited ? 'Remove from favorites' : 'Add to favorites'"
        >
          <svg class="icon" fill="currentColor" viewBox="0 0 20 20">
            <path 
              v-if="isFavorited"
              d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"
            />
            <path 
              v-else
              fill-rule="evenodd" 
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" 
              clip-rule="evenodd"
            />
          </svg>
        </button>

        <button 
          v-if="showMore"
          class="action-btn"
          @click.stop="$emit('more', package)"
          title="More options"
        >
          <svg class="icon" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Package Details -->
    <div class="card-body">
      <!-- Version Info -->
      <div class="version-info">
        <span class="version-label">Latest:</span>
        <span class="version-value">{{ package.latest_version || package.version || 'N/A' }}</span>
        
        <span v-if="package.release_date" class="release-date">
          {{ formatDate(package.release_date) }}
        </span>
      </div>

      <!-- Stats -->
      <div v-if="showStats" class="package-stats">
        <div v-if="package.downloads" class="stat">
          <svg class="stat-icon" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
          <span>{{ formatNumber(package.downloads) }}</span>
        </div>

        <div v-if="package.stars" class="stat">
          <svg class="stat-icon" fill="currentColor" viewBox="0 0 20 20">
            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/>
          </svg>
          <span>{{ formatNumber(package.stars) }}</span>
        </div>

        <div v-if="package.size" class="stat">
          <svg class="stat-icon" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M3 5a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2h-2.22l.123.489.804.804A1 1 0 0113 18H7a1 1 0 01-.707-1.707l.804-.804L7.22 15H5a2 2 0 01-2-2V5zm5.771 7H5V5h10v7H8.771z" clip-rule="evenodd"/>
          </svg>
          <span>{{ formatSize(package.size) }}</span>
        </div>
      </div>

      <!-- Tags/Categories -->
      <div v-if="package.tags && package.tags.length" class="package-tags">
        <span 
          v-for="tag in displayTags" 
          :key="tag"
          class="tag"
        >
          {{ tag }}
        </span>
        <span v-if="package.tags.length > maxTags" class="tag tag-more">
          +{{ package.tags.length - maxTags }}
        </span>
      </div>

      <!-- License -->
      <div v-if="package.license" class="package-license">
        <svg class="license-icon" fill="currentColor" viewBox="0 0 20 20">
          <path fill-rule="evenodd" d="M10 2L3 7v6c0 5.55 3.84 9.74 9 9 5.16.74 9-3.45 9-9V7l-7-5z" clip-rule="evenodd"/>
        </svg>
        <span>{{ package.license }}</span>
      </div>

      <!-- Compatibility Status -->
      <div v-if="package.compatible !== undefined" class="compatibility-status">
        <div 
          :class="[
            'compatibility-indicator',
            package.compatible ? 'compatible' : 'incompatible'
          ]"
        >
          <svg v-if="package.compatible" class="status-icon" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
          </svg>
          <svg v-else class="status-icon" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
          </svg>
          <span>{{ package.compatible ? 'Compatible' : 'Incompatible' }}</span>
        </div>
        
        <div v-if="package.compatibility_notes && package.compatibility_notes.length" class="compatibility-notes">
          <p v-for="note in package.compatibility_notes" :key="note" class="note">
            {{ note }}
          </p>
        </div>
      </div>
    </div>

    <!-- Card Footer -->
    <div v-if="$slots.footer || showInstall" class="card-footer">
      <slot name="footer">
        <button 
          v-if="showInstall"
          class="install-btn"
          @click.stop="$emit('install', package)"
          :disabled="loading"
        >
          <svg class="btn-icon" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clip-rule="evenodd"/>
          </svg>
          Install
        </button>
      </slot>
    </div>
  </div>
</template>

<script>
import LoadingSpinner from './LoadingSpinner.vue'

export default {
  name: 'PackageCard',
  components: {
    LoadingSpinner
  },
  emits: ['click', 'favorite', 'more', 'install'],
  
  props: {
    // Package data
    package: {
      type: Object,
      required: true
    },
    
    // Card state
    selected: {
      type: Boolean,
      default: false
    },
    
    loading: {
      type: Boolean,
      default: false
    },
    
    // Display options
    showStats: {
      type: Boolean,
      default: true
    },
    
    showFavorite: {
      type: Boolean,
      default: true
    },
    
    showMore: {
      type: Boolean,
      default: true
    },
    
    showInstall: {
      type: Boolean,
      default: true
    },
    
    // Text limits
    maxDescriptionLength: {
      type: Number,
      default: 120
    },
    
    maxTags: {
      type: Number,
      default: 3
    },
    
    // Favorites list
    favorites: {
      type: Array,
      default: () => []
    }
  },
  
  computed: {
    ecosystemDisplay() {
      const ecosystemNames = {
        pypi: 'PyPI',
        npm: 'NPM',
        conda: 'Conda',
        maven: 'Maven',
        crates: 'Crates'
      }
      return ecosystemNames[this.package.ecosystem] || this.package.ecosystem?.toUpperCase()
    },
    
    truncatedDescription() {
      if (!this.package.description) return ''
      if (this.package.description.length <= this.maxDescriptionLength) {
        return this.package.description
      }
      return this.package.description.slice(0, this.maxDescriptionLength) + '...'
    },
    
    displayTags() {
      if (!this.package.tags) return []
      return this.package.tags.slice(0, this.maxTags)
    },
    
    isFavorited() {
      return this.favorites.some(fav => 
        fav.name === this.package.name && 
        fav.ecosystem === this.package.ecosystem
      )
    }
  },
  
  methods: {
    handleClick() {
      if (!this.loading) {
        this.$emit('click', this.package)
      }
    },
    
    toggleFavorite() {
      this.$emit('favorite', {
        package: this.package,
        action: this.isFavorited ? 'remove' : 'add'
      })
    },
    
    formatDate(dateString) {
      if (!dateString) return ''
      try {
        const date = new Date(dateString)
        return date.toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric'
        })
      } catch {
        return dateString
      }
    },
    
    formatNumber(num) {
      if (!num) return '0'
      if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M'
      }
      if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K'
      }
      return num.toString()
    },
    
    formatSize(bytes) {
      if (!bytes) return ''
      const sizes = ['B', 'KB', 'MB', 'GB']
      const i = Math.floor(Math.log(bytes) / Math.log(1024))
      return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + sizes[i]
    }
  }
}
</script>

<style scoped>
.package-card {
  background: white;
  border: 1px solid #E5E7EB;
  border-radius: 0.5rem;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  position: relative;
  overflow: hidden;
}

.package-card:hover {
  border-color: #3B82F6;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.package-card.selected {
  border-color: #3B82F6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.package-card.loading {
  opacity: 0.7;
  cursor: not-allowed;
}

.loading-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.package-info {
  flex: 1;
  min-width: 0;
}

.package-name {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1F2937;
  margin: 0 0 0.5rem 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.ecosystem-badge {
  background: #F3F4F6;
  color: #374151;
  font-size: 0.75rem;
  font-weight: 500;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  text-transform: uppercase;
}

.package-description {
  font-size: 0.875rem;
  color: #6B7280;
  line-height: 1.4;
  margin: 0;
}

.card-actions {
  display: flex;
  gap: 0.5rem;
  margin-left: 1rem;
}

.action-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid #E5E7EB;
  border-radius: 0.375rem;
  background: white;
  color: #6B7280;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
}

.action-btn:hover {
  border-color: #9CA3AF;
  color: #374151;
}

.action-btn.favorited {
  color: #F59E0B;
  border-color: #F59E0B;
}

.action-btn .icon {
  width: 16px;
  height: 16px;
}

.card-body {
  space-y: 1rem;
}

.version-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.version-label {
  font-size: 0.875rem;
  color: #6B7280;
  font-weight: 500;
}

.version-value {
  font-size: 0.875rem;
  color: #1F2937;
  font-weight: 600;
  background: #F3F4F6;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.release-date {
  font-size: 0.75rem;
  color: #9CA3AF;
}

.package-stats {
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
}

.stat {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: #6B7280;
}

.stat-icon {
  width: 16px;
  height: 16px;
}

.package-tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.tag {
  background: #EFF6FF;
  color: #1D4ED8;
  font-size: 0.75rem;
  font-weight: 500;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
}

.tag-more {
  background: #F3F4F6;
  color: #6B7280;
}

.package-license {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #6B7280;
  margin-bottom: 1rem;
}

.license-icon {
  width: 16px;
  height: 16px;
}

.compatibility-status {
  margin-bottom: 1rem;
}

.compatibility-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
  margin-bottom: 0.5rem;
}

.compatibility-indicator.compatible {
  color: #059669;
}

.compatibility-indicator.incompatible {
  color: #DC2626;
}

.status-icon {
  width: 16px;
  height: 16px;
}

.compatibility-notes {
  font-size: 0.75rem;
  color: #6B7280;
}

.note {
  margin: 0.25rem 0;
}

.card-footer {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid #F3F4F6;
}

.install-btn {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: #3B82F6;
  color: white;
  border: none;
  border-radius: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  width: 100%;
  justify-content: center;
}

.install-btn:hover:not(:disabled) {
  background: #2563EB;
}

.install-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

/* Responsive Design */
@media (max-width: 640px) {
  .package-card {
    padding: 1rem;
  }
  
  .card-header {
    flex-direction: column;
    gap: 1rem;
  }
  
  .card-actions {
    margin-left: 0;
    align-self: flex-start;
  }
  
  .package-stats {
    flex-direction: column;
    gap: 0.5rem;
  }
}
</style>