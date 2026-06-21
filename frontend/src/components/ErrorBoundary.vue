<!-- frontend/src/components/ErrorBoundary.vue -->
<template>
  <div class="error-boundary">
    <!-- Error State -->
    <div v-if="hasError" class="error-container">
      <!-- Error Icon -->
      <div class="error-icon">
        <svg 
          class="icon" 
          fill="none" 
          stroke="currentColor" 
          viewBox="0 0 24 24"
        >
          <path 
            stroke-linecap="round" 
            stroke-linejoin="round" 
            stroke-width="2" 
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" 
          />
        </svg>
      </div>

      <!-- Error Content -->
      <div class="error-content">
        <h2 class="error-title">
          {{ errorTitle }}
        </h2>
        
        <p class="error-message">
          {{ errorMessage }}
        </p>

        <!-- Error Details (Development Only) -->
        <details v-if="showDetails && errorDetails" class="error-details">
          <summary class="error-details-summary">
            Error Details
          </summary>
          <pre class="error-details-content">{{ errorDetails }}</pre>
        </details>

        <!-- Error ID for Support -->
        <p v-if="errorId" class="error-id">
          Error ID: <code>{{ errorId }}</code>
        </p>
      </div>

      <!-- Action Buttons -->
      <div class="error-actions">
        <button 
          class="btn btn-primary"
          @click="handleRetry"
        >
          Try Again
        </button>
        
        <button 
          class="btn btn-secondary"
          @click="handleReload"
        >
          Reload Page
        </button>
        
        <button 
          v-if="showReportButton"
          class="btn btn-outline"
          @click="handleReport"
        >
          Report Issue
        </button>
      </div>
    </div>

    <!-- Normal Content -->
    <div v-else>
      <slot></slot>
    </div>
  </div>
</template>

<script>
export default {
  name: 'ErrorBoundary',
  emits: ['error', 'retry', 'report'],
  
  data() {
    return {
      hasError: false,
      error: null,
      errorInfo: null,
      errorId: null
    }
  },

  props: {
    // Custom error title
    fallbackTitle: {
      type: String,
      default: 'Something went wrong'
    },
    
    // Custom error message
    fallbackMessage: {
      type: String,
      default: 'An unexpected error has occurred. Please try again or contact support if the problem persists.'
    },
    
    // Show error details in development
    showDetails: {
      type: Boolean,
      default: process.env.NODE_ENV === 'development'
    },
    
    // Show report button
    showReportButton: {
      type: Boolean,
      default: true
    },
    
    // Auto retry after error
    autoRetry: {
      type: Boolean,
      default: false
    },
    
    // Auto retry delay (ms)
    retryDelay: {
      type: Number,
      default: 3000
    },
    
    // Maximum retry attempts
    maxRetries: {
      type: Number,
      default: 3
    }
  },

  computed: {
    errorTitle() {
      if (this.error?.title) return this.error.title
      if (this.error?.response?.status === 404) return 'Not Found'
      if (this.error?.response?.status === 403) return 'Access Denied'
      if (this.error?.response?.status === 500) return 'Server Error'
      if (this.error?.code === 'NETWORK_ERROR') return 'Connection Error'
      return this.fallbackTitle
    },

    errorMessage() {
      if (this.error?.message) return this.error.message
      if (this.error?.response?.data?.error?.message) return this.error.response.data.error.message
      if (this.error?.response?.status === 404) return 'The requested resource could not be found.'
      if (this.error?.response?.status === 403) return 'You do not have permission to access this resource.'
      if (this.error?.response?.status === 500) return 'A server error occurred. Please try again later.'
      if (this.error?.code === 'NETWORK_ERROR') return 'Unable to connect to the server. Please check your internet connection.'
      return this.fallbackMessage
    },

    errorDetails() {
      if (!this.showDetails) return null
      
      const details = {
        message: this.error?.message,
        stack: this.error?.stack,
        componentStack: this.errorInfo?.componentStack,
        props: this.$props,
        timestamp: new Date().toISOString()
      }
      
      if (this.error?.response) {
        details.response = {
          status: this.error.response.status,
          statusText: this.error.response.statusText,
          data: this.error.response.data
        }
      }
      
      return JSON.stringify(details, null, 2)
    }
  },

  created() {
    // Set up global error handler
    this.setupGlobalErrorHandler()
    
    // Set up unhandled promise rejection handler
    this.setupPromiseRejectionHandler()
  },

  beforeUnmount() {
    // Clean up error handlers
    this.cleanupErrorHandlers()
  },

  methods: {
    // Catch and handle errors
    captureError(error, errorInfo = null) {
      this.hasError = true
      this.error = error
      this.errorInfo = errorInfo
      this.errorId = this.generateErrorId()
      
      console.error('Error caught by ErrorBoundary:', error)
      
      // Emit error event
      this.$emit('error', {
        error,
        errorInfo,
        errorId: this.errorId
      })
      
      // Send error to monitoring service
      this.reportError(error, errorInfo)
      
      // Auto retry if enabled
      if (this.autoRetry && this.retryCount < this.maxRetries) {
        setTimeout(() => {
          this.handleRetry()
        }, this.retryDelay)
      }
    },

    // Generate unique error ID
    generateErrorId() {
      return `err_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    },

    // Handle retry action
    handleRetry() {
      this.hasError = false
      this.error = null
      this.errorInfo = null
      this.errorId = null
      
      this.$emit('retry')
      
      // Force re-render of child components
      this.$nextTick(() => {
        this.$forceUpdate()
      })
    },

    // Handle page reload
    handleReload() {
      window.location.reload()
    },

    // Handle error reporting
    handleReport() {
      const errorReport = {
        errorId: this.errorId,
        title: this.errorTitle,
        message: this.errorMessage,
        details: this.errorDetails,
        userAgent: navigator.userAgent,
        url: window.location.href,
        timestamp: new Date().toISOString()
      }
      
      this.$emit('report', errorReport)
      
      // You could also send to an error reporting service here
      this.submitErrorReport(errorReport)
    },

    // Submit error report to service
    async submitErrorReport(errorReport) {
      try {
        // Example: Send to your error reporting endpoint
        await fetch('/api/v1/errors/report', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(errorReport)
        })
        
        this.showToast('Error report submitted successfully', 'success')
      } catch (err) {
        console.error('Failed to submit error report:', err)
        this.showToast('Failed to submit error report', 'error')
      }
    },

    // Send error to monitoring service
    reportError(error, errorInfo) {
      // Example integrations:
      
      // Sentry
      if (window.Sentry) {
        window.Sentry.captureException(error, {
          extra: errorInfo,
          tags: {
            component: 'ErrorBoundary',
            errorId: this.errorId
          }
        })
      }
      
      // Custom logging service
      if (window.analytics) {
        window.analytics.track('Error Occurred', {
          error: error.message,
          stack: error.stack,
          errorId: this.errorId,
          url: window.location.href
        })
      }
    },

    // Setup global error handler
    setupGlobalErrorHandler() {
      this.originalErrorHandler = window.onerror
      
      window.onerror = (message, source, lineno, colno, error) => {
        this.captureError(error || new Error(message), {
          source,
          lineno,
          colno
        })
        
        // Call original handler if it exists
        if (this.originalErrorHandler) {
          return this.originalErrorHandler(message, source, lineno, colno, error)
        }
      }
    },

    // Setup promise rejection handler
    setupPromiseRejectionHandler() {
      this.originalRejectionHandler = window.onunhandledrejection
      
      window.onunhandledrejection = (event) => {
        this.captureError(event.reason, {
          type: 'unhandledrejection',
          promise: event.promise
        })
        
        // Call original handler if it exists
        if (this.originalRejectionHandler) {
          return this.originalRejectionHandler(event)
        }
      }
    },

    // Clean up error handlers
    cleanupErrorHandlers() {
      if (this.originalErrorHandler) {
        window.onerror = this.originalErrorHandler
      }
      
      if (this.originalRejectionHandler) {
        window.onunhandledrejection = this.originalRejectionHandler
      }
    },

    // Show toast notification
    showToast(message, type = 'info') {
      // This would integrate with your toast notification system
      console.log(`Toast (${type}): ${message}`)
    }
  },

  // Vue error handler
  errorCaptured(err, vm, info) {
    this.captureError(err, { info, vm })
    return false // Prevent the error from propagating further
  }
}
</script>

<style scoped>
.error-boundary {
  width: 100%;
  height: 100%;
}

.error-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  padding: 2rem;
  text-align: center;
}

.error-icon {
  margin-bottom: 1.5rem;
}

.error-icon .icon {
  width: 64px;
  height: 64px;
  color: #EF4444;
}

.error-content {
  max-width: 600px;
  margin-bottom: 2rem;
}

.error-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: #374151;
  margin: 0 0 1rem 0;
}

.error-message {
  font-size: 1rem;
  color: #6B7280;
  line-height: 1.6;
  margin: 0 0 1.5rem 0;
}

.error-details {
  text-align: left;
  margin: 1.5rem 0;
  border: 1px solid #E5E7EB;
  border-radius: 0.375rem;
  overflow: hidden;
}

.error-details-summary {
  padding: 0.75rem 1rem;
  background-color: #F9FAFB;
  cursor: pointer;
  font-weight: 500;
  border-bottom: 1px solid #E5E7EB;
}

.error-details-summary:hover {
  background-color: #F3F4F6;
}

.error-details-content {
  padding: 1rem;
  background-color: #1F2937;
  color: #F9FAFB;
  font-size: 0.75rem;
  line-height: 1.4;
  overflow-x: auto;
  margin: 0;
  white-space: pre-wrap;
}

.error-id {
  font-size: 0.875rem;
  color: #9CA3AF;
  margin: 1rem 0 0 0;
}

.error-id code {
  background-color: #F3F4F6;
  padding: 0.25rem 0.5rem;
  border-radius: 0.25rem;
  font-family: 'Courier New', monospace;
  font-size: 0.8rem;
}

.error-actions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
}

/* Button Styles */
.btn {
  padding: 0.75rem 1.5rem;
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
  min-width: 120px;
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
  background-color: #6B7280;
  color: white;
  border-color: #6B7280;
}

.btn-secondary:hover {
  background-color: #4B5563;
  border-color: #4B5563;
}

.btn-outline {
  background-color: transparent;
  color: #374151;
  border-color: #D1D5DB;
}

.btn-outline:hover {
  background-color: #F9FAFB;
  border-color: #9CA3AF;
}

/* Responsive Design */
@media (max-width: 640px) {
  .error-container {
    padding: 1.5rem 1rem;
    min-height: 300px;
  }
  
  .error-icon .icon {
    width: 48px;
    height: 48px;
  }
  
  .error-title {
    font-size: 1.25rem;
  }
  
  .error-actions {
    flex-direction: column;
    align-items: stretch;
  }
  
  .btn {
    width: 100%;
  }
}
</style>