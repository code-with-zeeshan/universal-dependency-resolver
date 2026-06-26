<template>
  <div class="app-wrapper">
    <div v-if="backendStatus === 'loading'" class="backend-banner backend-loading">
      <span class="backend-banner-dot"></span>
      <span>Connecting to backend...</span>
    </div>
    <div v-else-if="backendStatus === 'error'" class="backend-banner backend-error">
      <span>Backend unavailable. Make sure Python 3.11+ is installed and try restarting the application.</span>
    </div>

    <div class="app-layout">
      <aside class="sidebar">
        <div class="sidebar-header">
          <h1 class="text-lg font-bold">UDR</h1>
        </div>
        <nav class="sidebar-nav">
          <button v-for="item in navItems" :key="item.key"
                  @click="activeSection = item.key"
                  class="nav-btn" :class="{ 'nav-active': activeSection === item.key }">
            <component :is="item.icon" class="nav-icon" />
            <span>{{ item.label }}</span>
          </button>
        </nav>
      </aside>

      <main class="main-content">
        <DashboardPanel v-if="activeSection === 'dashboard'" @navigate="activeSection = $event" />
        <PackagePanel v-if="activeSection === 'packages'" />
        <ResolvePanel v-if="activeSection === 'resolve'" />
        <SystemPanel v-if="activeSection === 'system'" />
        <AuthPanel v-if="activeSection === 'auth'" />
        <ProjectScanPanel v-if="activeSection === 'scan'" />
      </main>
    </div>
  </div>
</template>

<script>
import { ref, onMounted } from 'vue'
import DashboardPanel from './components/DashboardPanel.vue'
import PackagePanel from './components/PackagePanel.vue'
import ResolvePanel from './components/ResolvePanel.vue'
import SystemPanel from './components/SystemPanel.vue'
import AuthPanel from './components/AuthPanel.vue'
import ProjectScanPanel from './components/ProjectScanPanel.vue'
import {
  HomeIcon, MagnifyingGlassIcon, CheckBadgeIcon,
  ServerIcon, LockClosedIcon, DocumentMagnifyingGlassIcon,
} from './icons'

export default {
  name: 'App',
  components: {
    DashboardPanel, PackagePanel, ResolvePanel, SystemPanel, AuthPanel, ProjectScanPanel,
    HomeIcon, MagnifyingGlassIcon, CheckBadgeIcon, ServerIcon, LockClosedIcon, DocumentMagnifyingGlassIcon,
  },
  setup() {
    const backendStatus = ref('loading')
    const activeSection = ref('dashboard')

    const navItems = [
      { key: 'dashboard', label: 'Dashboard', icon: HomeIcon },
      { key: 'packages', label: 'Packages', icon: MagnifyingGlassIcon },
      { key: 'resolve', label: 'Resolve', icon: CheckBadgeIcon },
      { key: 'system', label: 'System', icon: ServerIcon },
      { key: 'auth', label: 'Auth', icon: LockClosedIcon },
      { key: 'scan', label: 'Scan', icon: DocumentMagnifyingGlassIcon },
    ]

    onMounted(async () => {
      document.title = 'Universal Dependency Resolver'
      let backendUrl = 'http://127.0.0.1:8199'
      if (window.udrDesktop) {
        try {
          backendUrl = await window.udrDesktop.getBackendUrl()
        } catch (e) {
          console.warn('Could not get backend URL via IPC:', e)
        }
      } else if (window.__UDR_BACKEND_URL__) {
        backendUrl = window.__UDR_BACKEND_URL__
      }

      const maxRetries = 30
      for (let i = 0; i < maxRetries; i++) {
        try {
          const res = await fetch(`${backendUrl}/api/v1/health`, { method: 'GET' })
          if (res.ok || res.status === 200) {
            backendStatus.value = 'ready'
            return
          }
        } catch (e) {
          console.debug('Backend health check failed, retrying...', e.message)
        }
        if (window.__UDR_BACKEND_READY__) {
          backendStatus.value = 'ready'
          return
        }
        await new Promise(r => setTimeout(r, 2000))
      }
      backendStatus.value = 'error'
    })

    return { backendStatus, activeSection, navItems }
  }
}
</script>

<style>
@import 'tailwindcss/base';
@import 'tailwindcss/components';
@import 'tailwindcss/utilities';

.app-layout {
  display: flex;
  flex: 1;
  min-height: 0;
}

.sidebar {
  width: 200px;
  background: #1f2937;
  color: white;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 1.25rem;
  border-bottom: 1px solid #374151;
}

.sidebar-nav {
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.nav-btn {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  border: none;
  background: transparent;
  color: #d1d5db;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.15s;
  width: 100%;
  text-align: left;
}

.nav-btn:hover {
  background: #374151;
  color: white;
}

.nav-active {
  background: #3b82f6;
  color: white;
}

.nav-icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

.main-content {
  flex: 1;
  padding: 1.5rem;
  background: #f3f4f6;
  overflow-y: auto;
}

.panel {
  max-width: 1200px;
}

.panel-title {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 1.25rem;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  border-bottom: 2px solid #e5e7eb;
  padding-bottom: 0;
}

.tab {
  padding: 0.5rem 1rem;
  border: none;
  background: transparent;
  color: #6b7280;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.15s;
}

.tab:hover {
  color: #374151;
}

.tab-active {
  color: #3b82f6;
  border-bottom-color: #3b82f6;
}

.stat-card {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1rem;
}

.stat-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: #6b7280;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.stat-value {
  font-size: 1.125rem;
  font-weight: 700;
}

.btn {
  padding: 0.5rem 1rem;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  border: none;
  font-size: 0.875rem;
}

.btn-primary {
  background: #3b82f6;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #e5e7eb;
  color: #374151;
}

.btn-secondary:hover:not(:disabled) {
  background: #d1d5db;
}

.btn-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
}

.btn-lg {
  padding: 0.75rem 1.5rem;
  font-size: 1rem;
}

.form-input {
  padding: 0.5rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.15s;
}

.form-input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.form-select {
  padding: 0.5rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.875rem;
  background: white;
  outline: none;
}

.error-msg {
  background: #fef2f2;
  color: #dc2626;
  padding: 0.75rem 1rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.app-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.backend-banner {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  flex-shrink: 0;
}

.backend-loading {
  background: #eff6ff;
  color: #1d4ed8;
}

.backend-error {
  background: #fef2f2;
  color: #dc2626;
}

.backend-banner-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: #3b82f6;
  animation: pulse-dot 1.5s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
</style>
