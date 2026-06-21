// frontend/src/services/systemService.js
import axios from 'axios'

const API_BASE = process.env.VUE_APP_API_URL || 'http://localhost:8000'
const API_VERSION = 'v1'

class SystemService {
  constructor() {
    this.client = axios.create({
      baseURL: `${API_BASE}/api/${API_VERSION}`,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json'
      }
    })
    
    // Add request interceptor for authentication
    this.client.interceptors.request.use(
      (config) => {
        const token = localStorage.getItem('access_token'); 
        if (token) {
          config.headers.Authorization = `Bearer ${token}`
        }
        return config
      },
      (error) => {
        return Promise.reject(error)
      }
    )
    
    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        // Handle rate limiting
        if (error.response?.status === 429) {
          console.error('Rate limit exceeded. Please try again later.')
          // Could implement retry logic here
        }
        
        // Handle authentication errors
        if (error.response?.status === 401) {
          localStorage.removeItem('authToken')
          // window.location.href = '/login'
        }
        
        return Promise.reject(error)
      }
    )
    
    // Cache system info for 5 minutes
    this.cache = {
      systemInfo: null,
      timestamp: null,
      ttl: 5 * 60 * 1000 // 5 minutes
    }
  }

  async getSystemInfo(detailed = false, forceRefresh = false) {
    try {
      // Check cache
      if (!forceRefresh && this.cache.systemInfo && this.cache.timestamp) {
        const age = Date.now() - this.cache.timestamp
        if (age < this.cache.ttl) {
          return this.cache.systemInfo
        }
      }
      
      const response = await this.client.get('/system/info', {
        params: { detailed }
      })
      
      const systemInfo = response.data.data // || response.data.system
      
      // Update cache
      this.cache.systemInfo = systemInfo
      this.cache.timestamp = Date.now()
      
      return systemInfo
    } catch (error) {
      console.error('Get system info error:', error)
      throw this.handleError(error)
    }
  }

  async checkCompatibility(requirements, packages = null) {
    try {
      const data = {
        requirements
      }
      
      if (packages) {
        data.packages = packages
      }
      
      const response = await this.client.post('/system/check-compatibility', data)
      return response.data.results || response.data
    } catch (error) {
      console.error('Check compatibility error:', error)
      throw this.handleError(error)
    }
  }

  async getGpuInfo() {
    try {
      const response = await this.client.get('/system/gpu/info')
      return response.data.gpu || response.data
    } catch (error) {
      console.error('Get GPU info error:', error)
      throw this.handleError(error)
    }
  }

  async getRuntimeInfo(runtime) {
    try {
      const response = await this.client.get(`/system/runtime/${runtime}`)
      return response.data.info || response.data
    } catch (error) {
      console.error(`Get ${runtime} info error:`, error)
      throw this.handleError(error)
    }
  }

  async analyzeEnvironmentFile(file) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      
      const response = await this.client.post('/system/analyze-environment', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      })
      
      return response.data.analysis || response.data
    } catch (error) {
      console.error('Analyze environment file error:', error)
      throw this.handleError(error)
    }
  }

  async runBenchmarks(comprehensive = false) {
    try {
      const params = {}
      if (comprehensive) {
        params.comprehensive = true
      }
      
      // Benchmarks may take longer, so increase timeout
      const response = await this.client.get('/system/benchmarks', {
        params,
        timeout: 60000 // 60 seconds for benchmarks
      })
      
      return response.data.benchmarks || response.data
    } catch (error) {
      console.error('Run benchmarks error:', error)
      throw this.handleError(error)
    }
  }

  async getHealthStatus() {
    try {
      const response = await this.client.get('/health')
      return response.data
    } catch (error) {
      console.error('Error fetching health status:', error)
      throw this.handleError(error)
    }
  }

  // Helper method to format system requirements from system info
  formatSystemRequirements(systemInfo) {
    const requirements = []
    
    if (systemInfo.gpu?.available) {
      requirements.push({
        type: 'gpu',
        name: 'GPU',
        value: systemInfo.gpu.devices[0]?.name,
        metadata: {
          cuda: systemInfo.gpu.cuda,
          cudnn: systemInfo.gpu.cudnn,
          driver: systemInfo.gpu.driver_version
        }
      })
    }
    
    if (systemInfo.runtime_versions?.python) {
      requirements.push({
        type: 'python',
        name: 'Python',
        value: systemInfo.runtime_versions.python.version,
        metadata: {
          location: systemInfo.runtime_versions.python.location
        }
      })
    }
    
    if (systemInfo.os) {
      requirements.push({
        type: 'os',
        name: 'Operating System',
        value: `${systemInfo.os.system} ${systemInfo.os.release}`,
        metadata: {
          platform: systemInfo.os.platform,
          architecture: systemInfo.os.machine,
          version: systemInfo.os.version
        }
      })
    }
    
    if (systemInfo.cpu) {
      requirements.push({
        type: 'cpu',
        name: 'CPU',
        value: systemInfo.cpu.brand,
        metadata: {
          cores: systemInfo.cpu.count || systemInfo.cpu.physical_cores,
          threads: systemInfo.cpu.logical_cores,
          architecture: systemInfo.cpu.arch
        }
      })
    }
    
    if (systemInfo.memory) {
      requirements.push({
        type: 'memory',
        name: 'RAM',
        value: this.formatBytes(systemInfo.memory.total),
        metadata: {
          total: systemInfo.memory.total,
          available: systemInfo.memory.available
        }
      })
    }
    
    return requirements
  }

  // Compare system requirements with package requirements
  compareSystemRequirements(systemInfo, requirements) {
    const comparison = {
      compatible: true,
      issues: [],
      warnings: []
    }
    
    // Check GPU requirements
    if (requirements.gpu) {
      if (!systemInfo.gpu?.available) {
        comparison.compatible = false
        comparison.issues.push('GPU required but not available')
      } else if (requirements.gpu.cuda) {
        const systemCuda = parseFloat(systemInfo.gpu.cuda || '0')
        const requiredCuda = parseFloat(requirements.gpu.cuda)
        
        if (systemCuda < requiredCuda) {
          comparison.compatible = false
          comparison.issues.push(
            `CUDA ${requirements.gpu.cuda} required, but ${systemInfo.gpu.cuda || 'not installed'} found`
          )
        }
      }
      
      // Check GPU memory if specified
      if (requirements.gpu.memory && systemInfo.gpu.devices?.[0]?.memory) {
        const systemMemory = systemInfo.gpu.devices[0].memory
        const requiredMemory = requirements.gpu.memory
        
        if (systemMemory < requiredMemory) {
          comparison.warnings.push(
            `GPU memory ${this.formatBytes(requiredMemory)} recommended, but ${this.formatBytes(systemMemory)} available`
          )
        }
      }
    }
    
    // Check Python version
    if (requirements.python) {
      const systemPython = systemInfo.runtime_versions?.python?.version
      if (!systemPython) {
        comparison.compatible = false
        comparison.issues.push('Python not detected')
      } else {
        const compatible = this.checkVersionCompatibility(
          systemPython,
          requirements.python,
          requirements.python_max
        )
        
        if (!compatible.compatible) {
          comparison.compatible = false
          comparison.issues.push(compatible.message)
        }
      }
    }
    
    // Check OS requirements
    if (requirements.os) {
      const systemOS = systemInfo.os?.system?.toLowerCase()
      const requiredOS = Array.isArray(requirements.os) 
        ? requirements.os.map(os => os.toLowerCase())
        : [requirements.os.toLowerCase()]
      
      if (!requiredOS.includes(systemOS)) {
        comparison.compatible = false
        comparison.issues.push(
          `Operating system ${requirements.os} required, but ${systemInfo.os.system} found`
        )
      }
    }
    
    // Check memory requirements
    if (requirements.memory && systemInfo.memory) {
      const systemMemory = systemInfo.memory.total
      const requiredMemory = requirements.memory
      
      if (systemMemory < requiredMemory) {
        comparison.warnings.push(
          `${this.formatBytes(requiredMemory)} RAM recommended, but ${this.formatBytes(systemMemory)} available`
        )
      }
    }
    
    return comparison
  }

  // Helper method to check version compatibility
  checkVersionCompatibility(systemVersion, minVersion, maxVersion = null) {
    const result = {
      compatible: true,
      message: ''
    }
    
    const systemParts = systemVersion.split('.').map(Number)
    const minParts = minVersion.split('.').map(Number)
    
    // Check minimum version
    for (let i = 0; i < Math.max(systemParts.length, minParts.length); i++) {
      const sys = systemParts[i] || 0
      const min = minParts[i] || 0
      
      if (sys < min) {
        result.compatible = false
        result.message = `Version ${minVersion} or higher required, but ${systemVersion} found`
        break
      } else if (sys > min) {
        break
      }
    }
    
    // Check maximum version if specified
    if (maxVersion && result.compatible) {
      const maxParts = maxVersion.split('.').map(Number)
      
      for (let i = 0; i < Math.max(systemParts.length, maxParts.length); i++) {
        const sys = systemParts[i] || 0
        const max = maxParts[i] || 0
        
        if (sys > max) {
          result.compatible = false
          result.message = `Version ${maxVersion} or lower required, but ${systemVersion} found`
          break
        } else if (sys < max) {
          break
        }
      }
    }
    
    return result
  }

  // Helper method to format bytes to human readable
  formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes'
    
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB']
    
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
  }

  // Helper method to format system info for display
  formatSystemInfo(systemInfo) {
    if (!systemInfo) return null
    
    return {
      os: {
        name: `${systemInfo.os.system} ${systemInfo.os.release}`,
        version: systemInfo.os.version,
        architecture: systemInfo.os.machine,
        platform: systemInfo.os.platform
      },
      cpu: {
        model: systemInfo.cpu.brand,
        cores: systemInfo.cpu.physical_cores || systemInfo.cpu.count,
        threads: systemInfo.cpu.logical_cores,
        frequency: systemInfo.cpu.frequency,
        architecture: systemInfo.cpu.arch
      },
      gpu: systemInfo.gpu.available ? {
        available: true,
        devices: systemInfo.gpu.devices,
        cuda: systemInfo.gpu.cuda,
        cudnn: systemInfo.gpu.cudnn,
        driver: systemInfo.gpu.driver_version
      } : {
        available: false
      },
      memory: {
        total: this.formatBytes(systemInfo.memory?.total || 0),
        available: this.formatBytes(systemInfo.memory?.available || 0),
        used: this.formatBytes(
          (systemInfo.memory?.total || 0) - (systemInfo.memory?.available || 0)
        ),
        percentage: systemInfo.memory?.total 
          ? Math.round(((systemInfo.memory.total - systemInfo.memory.available) / systemInfo.memory.total) * 100)
          : 0
      },
      python: systemInfo.runtime_versions?.python ? {
        version: systemInfo.runtime_versions.python.version,
        location: systemInfo.runtime_versions.python.location
      } : null,
      node: systemInfo.runtime_versions?.node || null,
      java: systemInfo.runtime_versions?.java || null
    }
  }

  // Helper method to handle errors consistently
  handleError(error) {
    if (error.response) {
      // Server responded with error
      const errorData = error.response.data?.error || error.response.data
      return {
        message: errorData.message || 'An error occurred',
        status: error.response.status,
        type: errorData.type || 'unknown',
        details: errorData.details || null
      }
    } else if (error.request) {
      // Request made but no response
      return {
        message: 'No response from server. Please check your connection.',
        status: 0,
        type: 'network_error'
      }
    } else {
      // Something else happened
      return {
        message: error.message || 'An unexpected error occurred',
        status: 0,
        type: 'client_error'
      }
    }
  }

  // Clear cache
  clearCache() {
    this.cache.systemInfo = null
    this.cache.timestamp = null
  }
}

export default new SystemService()