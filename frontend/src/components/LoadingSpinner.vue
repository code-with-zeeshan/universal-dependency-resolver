<!-- frontend/src/components/LoadingSpinner.vue -->
<template>
  <div 
    :class="[
      'loading-spinner',
      sizeClasses,
      colorClasses,
      { 'absolute-center': center }
    ]"
  >
    <div class="spinner-container">
      <!-- Spinner Animation -->
      <div 
        v-if="type === 'spinner'"
        class="spinner"
      >
        <div class="bounce1"></div>
        <div class="bounce2"></div>
        <div class="bounce3"></div>
      </div>

      <!-- Dots Animation -->
      <div 
        v-else-if="type === 'dots'"
        class="dots-spinner"
      >
        <div class="dot1"></div>
        <div class="dot2"></div>
        <div class="dot3"></div>
      </div>

      <!-- Pulse Animation -->
      <div 
        v-else-if="type === 'pulse'"
        class="pulse-spinner"
      ></div>

      <!-- Ring Animation -->
      <div 
        v-else-if="type === 'ring'"
        class="ring-spinner"
      >
        <div></div>
        <div></div>
        <div></div>
        <div></div>
      </div>

      <!-- Default Circular Spinner -->
      <div 
        v-else
        class="circular-spinner"
      ></div>

      <!-- Loading Text -->
      <div 
        v-if="text"
        class="loading-text"
      >
        {{ text }}
      </div>
    </div>

    <!-- Overlay for full-screen loading -->
    <div 
      v-if="overlay"
      class="loading-overlay"
      @click="$emit('cancel')"
    ></div>
  </div>
</template>

<script>
export default {
  name: 'LoadingSpinner',
  emits: ['cancel'],
  props: {
    // Spinner type
    type: {
      type: String,
      default: 'circular',
      validator: (value) => ['spinner', 'dots', 'pulse', 'ring', 'circular'].includes(value)
    },
    
    // Size
    size: {
      type: String,
      default: 'medium',
      validator: (value) => ['small', 'medium', 'large', 'extra-large'].includes(value)
    },
    
    // Color theme
    color: {
      type: String,
      default: 'primary',
      validator: (value) => ['primary', 'secondary', 'success', 'warning', 'error', 'white'].includes(value)
    },
    
    // Loading text
    text: {
      type: String,
      default: ''
    },
    
    // Center the spinner
    center: {
      type: Boolean,
      default: false
    },
    
    // Full screen overlay
    overlay: {
      type: Boolean,
      default: false
    }
  },
  
  computed: {
    sizeClasses() {
      return {
        'size-small': this.size === 'small',
        'size-medium': this.size === 'medium',
        'size-large': this.size === 'large',
        'size-extra-large': this.size === 'extra-large'
      }
    },
    
    colorClasses() {
      return {
        'color-primary': this.color === 'primary',
        'color-secondary': this.color === 'secondary',
        'color-success': this.color === 'success',
        'color-warning': this.color === 'warning',
        'color-error': this.color === 'error',
        'color-white': this.color === 'white'
      }
    }
  }
}
</script>

<style scoped>
.loading-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.absolute-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 100;
}

.spinner-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.loading-text {
  font-size: 0.875rem;
  font-weight: 500;
  text-align: center;
  color: #6B7280;
}

.loading-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 99;
  cursor: pointer;
}

/* Circular Spinner */
.circular-spinner {
  border: 3px solid #f3f3f3;
  border-top: 3px solid #3498db;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

/* Bounce Spinner */
.spinner {
  display: flex;
  gap: 3px;
}

.spinner > div {
  border-radius: 100%;
  display: inline-block;
  animation: sk-bouncedelay 1.4s infinite ease-in-out both;
}

.spinner .bounce1 {
  animation-delay: -0.32s;
}

.spinner .bounce2 {
  animation-delay: -0.16s;
}

/* Dots Spinner */
.dots-spinner {
  display: flex;
  gap: 4px;
}

.dots-spinner > div {
  border-radius: 100%;
  display: inline-block;
  animation: sk-bounce 1.4s infinite ease-in-out both;
}

.dots-spinner .dot1 {
  animation-delay: -0.32s;
}

.dots-spinner .dot2 {
  animation-delay: -0.16s;
}

/* Pulse Spinner */
.pulse-spinner {
  border-radius: 100%;
  animation: sk-pulse 1s infinite ease-in-out;
}

/* Ring Spinner */
.ring-spinner {
  display: inline-block;
  position: relative;
}

.ring-spinner div {
  box-sizing: border-box;
  display: block;
  position: absolute;
  border: 2px solid;
  border-radius: 50%;
  animation: lds-ring 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
  border-color: transparent;
}

.ring-spinner div:nth-child(1) {
  animation-delay: -0.45s;
  border-top-color: currentColor;
}

.ring-spinner div:nth-child(2) {
  animation-delay: -0.3s;
  border-right-color: currentColor;
}

.ring-spinner div:nth-child(3) {
  animation-delay: -0.15s;
  border-bottom-color: currentColor;
}

.ring-spinner div:nth-child(4) {
  border-left-color: currentColor;
}

/* Size Classes */
.size-small .circular-spinner,
.size-small .pulse-spinner {
  width: 20px;
  height: 20px;
}

.size-small .spinner > div,
.size-small .dots-spinner > div {
  width: 4px;
  height: 4px;
}

.size-small .ring-spinner {
  width: 20px;
  height: 20px;
}

.size-small .ring-spinner div {
  width: 16px;
  height: 16px;
  margin: 2px;
}

.size-medium .circular-spinner,
.size-medium .pulse-spinner {
  width: 32px;
  height: 32px;
}

.size-medium .spinner > div,
.size-medium .dots-spinner > div {
  width: 6px;
  height: 6px;
}

.size-medium .ring-spinner {
  width: 32px;
  height: 32px;
}

.size-medium .ring-spinner div {
  width: 26px;
  height: 26px;
  margin: 3px;
}

.size-large .circular-spinner,
.size-large .pulse-spinner {
  width: 48px;
  height: 48px;
}

.size-large .spinner > div,
.size-large .dots-spinner > div {
  width: 8px;
  height: 8px;
}

.size-large .ring-spinner {
  width: 48px;
  height: 48px;
}

.size-large .ring-spinner div {
  width: 40px;
  height: 40px;
  margin: 4px;
}

.size-extra-large .circular-spinner,
.size-extra-large .pulse-spinner {
  width: 64px;
  height: 64px;
}

.size-extra-large .spinner > div,
.size-extra-large .dots-spinner > div {
  width: 12px;
  height: 12px;
}

.size-extra-large .ring-spinner {
  width: 64px;
  height: 64px;
}

.size-extra-large .ring-spinner div {
  width: 54px;
  height: 54px;
  margin: 5px;
}

/* Color Classes */
.color-primary .circular-spinner {
  border-top-color: #3B82F6;
}

.color-primary .spinner > div,
.color-primary .dots-spinner > div,
.color-primary .pulse-spinner {
  background-color: #3B82F6;
}

.color-primary .ring-spinner {
  color: #3B82F6;
}

.color-secondary .circular-spinner {
  border-top-color: #6B7280;
}

.color-secondary .spinner > div,
.color-secondary .dots-spinner > div,
.color-secondary .pulse-spinner {
  background-color: #6B7280;
}

.color-secondary .ring-spinner {
  color: #6B7280;
}

.color-success .circular-spinner {
  border-top-color: #10B981;
}

.color-success .spinner > div,
.color-success .dots-spinner > div,
.color-success .pulse-spinner {
  background-color: #10B981;
}

.color-success .ring-spinner {
  color: #10B981;
}

.color-warning .circular-spinner {
  border-top-color: #F59E0B;
}

.color-warning .spinner > div,
.color-warning .dots-spinner > div,
.color-warning .pulse-spinner {
  background-color: #F59E0B;
}

.color-warning .ring-spinner {
  color: #F59E0B;
}

.color-error .circular-spinner {
  border-top-color: #EF4444;
}

.color-error .spinner > div,
.color-error .dots-spinner > div,
.color-error .pulse-spinner {
  background-color: #EF4444;
}

.color-error .ring-spinner {
  color: #EF4444;
}

.color-white .circular-spinner {
  border-top-color: #FFFFFF;
  border-color: rgba(255, 255, 255, 0.3);
}

.color-white .spinner > div,
.color-white .dots-spinner > div,
.color-white .pulse-spinner {
  background-color: #FFFFFF;
}

.color-white .ring-spinner {
  color: #FFFFFF;
}

.color-white .loading-text {
  color: #FFFFFF;
}

/* Animations */
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}

@keyframes sk-bouncedelay {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1.0);
  }
}

@keyframes sk-bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1.0);
  }
}

@keyframes sk-pulse {
  0% {
    transform: scale(0);
  }
  100% {
    transform: scale(1.0);
    opacity: 0;
  }
}

@keyframes lds-ring {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}
</style>