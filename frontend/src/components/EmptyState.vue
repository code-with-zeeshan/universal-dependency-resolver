<!-- frontend/src/components/EmptyState.vue -->
<template>
  <div :class="['empty-state', sizeClasses]">
    <!-- Icon Section -->
    <div class="empty-state-icon">
      <!-- Custom Icon Slot -->
      <slot name="icon">
        <!-- Default Icons based on type -->
        <svg 
          v-if="type === 'search'"
          class="icon"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
          />
        </svg>
        
        <svg 
          v-else-if="type === 'data'"
          class="icon"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
          />
        </svg>
        
        <svg 
          v-else-if="type === 'error'"
          class="icon"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        
        <svg 
          v-else-if="type === 'package'"
          class="icon"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
          />
        </svg>
        
        <svg 
          v-else
          class="icon"
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
          />
        </svg>
      </slot>
    </div>

    <!-- Content Section -->
    <div class="empty-state-content">
      <!-- Title -->
      <h3 v-if="title" class="empty-state-title">
        {{ title }}
      </h3>

      <!-- Description -->
      <p v-if="description" class="empty-state-description">
        {{ description }}
      </p>

      <!-- Custom Content Slot -->
      <div v-if="$slots.default" class="empty-state-custom">
        <slot></slot>
      </div>
    </div>

    <!-- Actions Section -->
    <div v-if="$slots.actions || primaryAction || secondaryAction" class="empty-state-actions">
      <!-- Custom Actions Slot -->
      <slot name="actions">
        <!-- Default Action Buttons -->
        <button 
          v-if="primaryAction"
          class="btn btn-primary"
          @click="$emit('primary-action')"
        >
          {{ primaryAction }}
        </button>
        
        <button 
          v-if="secondaryAction"
          class="btn btn-secondary"
          @click="$emit('secondary-action')"
        >
          {{ secondaryAction }}
        </button>
      </slot>
    </div>
  </div>
</template>

<script>
export default {
  name: 'EmptyState',
  emits: ['primary-action', 'secondary-action'],
  props: {
    // Type of empty state
    type: {
      type: String,
      default: 'default',
      validator: (value) => ['default', 'search', 'data', 'error', 'package'].includes(value)
    },
    
    // Size of the empty state
    size: {
      type: String,
      default: 'medium',
      validator: (value) => ['small', 'medium', 'large'].includes(value)
    },
    
    // Title text
    title: {
      type: String,
      default: ''
    },
    
    // Description text
    description: {
      type: String,
      default: ''
    },
    
    // Primary action button text
    primaryAction: {
      type: String,
      default: ''
    },
    
    // Secondary action button text
    secondaryAction: {
      type: String,
      default: ''
    }
  },
  
  computed: {
    sizeClasses() {
      return {
        'size-small': this.size === 'small',
        'size-medium': this.size === 'medium',
        'size-large': this.size === 'large'
      }
    }
  }
}
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 2rem;
  color: #6B7280;
}

.empty-state-icon {
  margin-bottom: 1.5rem;
}

.icon {
  width: 64px;
  height: 64px;
  color: #D1D5DB;
}

.empty-state-content {
  margin-bottom: 2rem;
  max-width: 400px;
}

.empty-state-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #374151;
  margin: 0 0 0.5rem 0;
}

.empty-state-description {
  font-size: 0.875rem;
  color: #6B7280;
  line-height: 1.5;
  margin: 0;
}

.empty-state-custom {
  margin-top: 1rem;
}

.empty-state-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: center;
}

/* Button Styles */
.btn {
  padding: 0.5rem 1rem;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  font-weight: 500;
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn:focus {
  outline: 2px solid transparent;
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.btn-primary {
  background-color: #3B82F6;
  color: white;
  border-color: #3B82F6;
}

.btn-primary:hover {
  background-color: #2563EB;
  border-color: #2563EB;
}

.btn-secondary {
  background-color: transparent;
  color: #374151;
  border-color: #D1D5DB;
}

.btn-secondary:hover {
  background-color: #F9FAFB;
  border-color: #9CA3AF;
}

/* Size Variations */
.size-small {
  padding: 1rem;
}

.size-small .icon {
  width: 48px;
  height: 48px;
}

.size-small .empty-state-icon {
  margin-bottom: 1rem;
}

.size-small .empty-state-content {
  margin-bottom: 1.5rem;
  max-width: 300px;
}

.size-small .empty-state-title {
  font-size: 1rem;
}

.size-small .empty-state-description {
  font-size: 0.8rem;
}

.size-medium {
  padding: 2rem;
}

.size-large {
  padding: 3rem;
}

.size-large .icon {
  width: 80px;
  height: 80px;
}

.size-large .empty-state-icon {
  margin-bottom: 2rem;
}

.size-large .empty-state-content {
  margin-bottom: 2.5rem;
  max-width: 500px;
}

.size-large .empty-state-title {
  font-size: 1.5rem;
}

.size-large .empty-state-description {
  font-size: 1rem;
}

/* Responsive Design */
@media (max-width: 640px) {
  .empty-state {
    padding: 1.5rem 1rem;
  }
  
  .empty-state-actions {
    flex-direction: column;
    align-items: stretch;
  }
  
  .btn {
    width: 100%;
  }
}
</style>