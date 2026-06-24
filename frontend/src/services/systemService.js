import apiClient from './apiClient'
import { filesize } from 'filesize'
import { satisfies } from 'semver'

class SystemService {
  constructor() {
    this.client = apiClient

    this.cache = {
      systemInfo: null,
      timestamp: null,
      ttl: 5 * 60 * 1000
    }
  }

  async getSystemInfo(detailed = true, forceRefresh = false) {
    try {
      if (!forceRefresh && this.cache.systemInfo && this.cache.timestamp) {
        const age = Date.now() - this.cache.timestamp
        if (age < this.cache.ttl) {
          return this.cache.systemInfo
        }
      }

      const response = await this.client.get('/system/info', {
        params: { detailed }
      })

      const systemInfo = response.data.data

      this.cache.systemInfo = systemInfo
      this.cache.timestamp = Date.now()

      return systemInfo
    } catch (error) {
      console.error('Get system info error:', error)
      throw error
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
      throw error
    }
  }

  async getGpuInfo() {
    try {
      const response = await this.client.get('/system/gpu/info')
      return response.data.gpu || response.data
    } catch (error) {
      console.error('Get GPU info error:', error)
      throw error
    }
  }

  async getRuntimeInfo(runtime) {
    try {
      const response = await this.client.get(`/system/runtime/${runtime}`)
      return response.data.info || response.data
    } catch (error) {
      console.error(`Get ${runtime} info error:`, error)
      throw error
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
      throw error
    }
  }

  async runBenchmarks(comprehensive = false) {
    try {
      const params = {}
      if (comprehensive) {
        params.comprehensive = true
      }

      const response = await this.client.get('/system/benchmarks', {
        params,
        timeout: 60000
      })

      return response.data.benchmarks || response.data
    } catch (error) {
      console.error('Run benchmarks error:', error)
      throw error
    }
  }

  async getHealthStatus() {
    try {
      const response = await this.client.get('/health')
      return response.data
    } catch (error) {
      console.error('Error fetching health status:', error)
      throw error
    }
  }

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

    if (systemInfo.platform) {
      requirements.push({
        type: 'os',
        name: 'Operating System',
        value: `${systemInfo.platform.system} ${systemInfo.platform.release}`,
        metadata: {
          platform: systemInfo.platform.system,
          architecture: systemInfo.platform.machine,
          version: systemInfo.platform.release
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
        value: filesize(systemInfo.memory.total),
        metadata: {
          total: systemInfo.memory.total,
          available: systemInfo.memory.available
        }
      })
    }

    return requirements
  }

  compareSystemRequirements(systemInfo, requirements) {
    const comparison = {
      compatible: true,
      issues: [],
      warnings: []
    }

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

      if (requirements.gpu.memory && systemInfo.gpu.devices?.[0]?.memory) {
        const systemMemory = systemInfo.gpu.devices[0].memory
        const requiredMemory = requirements.gpu.memory

        if (systemMemory < requiredMemory) {
          comparison.warnings.push(
            `GPU memory ${filesize(requiredMemory)} recommended, but ${filesize(systemMemory)} available`
          )
        }
      }
    }

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

    if (requirements.os) {
      const systemOS = systemInfo.platform?.system?.toLowerCase()
      const requiredOS = Array.isArray(requirements.os)
        ? requirements.os.map(os => os.toLowerCase())
        : [requirements.os.toLowerCase()]

      if (!requiredOS.includes(systemOS)) {
        comparison.compatible = false
        comparison.issues.push(
          `Operating system ${requirements.os} required, but ${systemInfo.platform?.system} found`
        )
      }
    }

    if (requirements.memory && systemInfo.memory) {
      const systemMemory = systemInfo.memory.total
      const requiredMemory = requirements.memory

      if (systemMemory < requiredMemory) {
        comparison.warnings.push(
          `${filesize(requiredMemory)} RAM recommended, but ${filesize(systemMemory)} available`
        )
      }
    }

    return comparison
  }

  checkVersionCompatibility(systemVersion, minVersion, maxVersion = null) {
    let range = `>=${minVersion}`
    if (maxVersion) {
      range += ` <=${maxVersion}`
    }
    const compatible = satisfies(systemVersion, range)
    return {
      compatible,
      message: compatible ? '' : `Version ${range} required, but ${systemVersion} found`
    }
  }

  formatSystemInfo(systemInfo) {
    if (!systemInfo) return null

    return {
      os: {
        name: `${systemInfo.platform.system} ${systemInfo.platform.release}`,
        version: systemInfo.platform.release,
        architecture: systemInfo.platform.machine,
        platform: systemInfo.platform.system
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
        total: filesize(systemInfo.memory?.total || 0),
        available: filesize(systemInfo.memory?.available || 0),
        used: filesize(
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

  clearCache() {
    this.cache.systemInfo = null
    this.cache.timestamp = null
  }
}

export default new SystemService()
