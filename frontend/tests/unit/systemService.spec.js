import systemService from '@/services/systemService'
import apiClient from '@/services/apiClient'

jest.mock('@/services/apiClient')

jest.mock('filesize', () => {
  return jest.fn((bytes) => {
    if (bytes === 0) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    const val = (bytes / Math.pow(1024, i)).toFixed(2)
    return `${val} ${units[i]}`
  })
})

describe('systemService', () => {
  afterEach(() => {
    jest.clearAllMocks()
    systemService.clearCache()
  })

  describe('getSystemInfo', () => {
    it('calls /system/info and returns data', async () => {
      apiClient.get.mockResolvedValue({
        data: { data: { platform: { system: 'Linux' }, cpu: { brand: 'Intel' } } }
      })

      const result = await systemService.getSystemInfo()

      expect(apiClient.get).toHaveBeenCalledWith('/system/info', { params: { detailed: false } })
      expect(result.platform.system).toBe('Linux')
    })

    it('caches results within TTL', async () => {
      apiClient.get.mockResolvedValue({
        data: { data: { platform: { system: 'Linux' } } }
      })

      await systemService.getSystemInfo()
      await systemService.getSystemInfo()

      expect(apiClient.get).toHaveBeenCalledTimes(1)
    })

    it('bypasses cache when forceRefresh is true', async () => {
      apiClient.get.mockResolvedValue({
        data: { data: { platform: { system: 'Linux' } } }
      })

      await systemService.getSystemInfo()
      await systemService.getSystemInfo(false, true)

      expect(apiClient.get).toHaveBeenCalledTimes(2)
    })

    it('throws on API error', async () => {
      apiClient.get.mockRejectedValue(new Error('API error'))

      await expect(systemService.getSystemInfo()).rejects.toThrow('API error')
    })
  })

  describe('checkCompatibility', () => {
    it('posts requirements and returns results', async () => {
      apiClient.post.mockResolvedValue({
        data: { results: { compatible: true } }
      })

      const result = await systemService.checkCompatibility({ gpu: { cuda: '11.0' } }, ['tensorflow'])

      expect(apiClient.post).toHaveBeenCalledWith('/system/check-compatibility', {
        requirements: { gpu: { cuda: '11.0' } },
        packages: ['tensorflow']
      })
      expect(result).toEqual({ compatible: true })
    })
  })

  describe('getGpuInfo', () => {
    it('calls /system/gpu/info', async () => {
      apiClient.get.mockResolvedValue({
        data: { gpu: { available: true, devices: [{ name: 'RTX 3080' }] } }
      })

      const result = await systemService.getGpuInfo()

      expect(apiClient.get).toHaveBeenCalledWith('/system/gpu/info')
      expect(result.available).toBe(true)
    })
  })

  describe('getRuntimeInfo', () => {
    it('calls runtime endpoint', async () => {
      apiClient.get.mockResolvedValue({
        data: { info: { version: '3.11.0' } }
      })

      const result = await systemService.getRuntimeInfo('python')

      expect(apiClient.get).toHaveBeenCalledWith('/system/runtime/python')
      expect(result.version).toBe('3.11.0')
    })
  })

  describe('analyzeEnvironmentFile', () => {
    it('posts FormData to analyze endpoint', async () => {
      apiClient.post.mockResolvedValue({
        data: { analysis: { packages: ['flask'] } }
      })

      const file = new File(['flask>=2.0'], 'requirements.txt')
      const result = await systemService.analyzeEnvironmentFile(file)

      expect(apiClient.post).toHaveBeenCalledWith(
        '/system/analyze-environment',
        expect.any(FormData),
        { headers: { 'Content-Type': 'multipart/form-data' } }
      )
      expect(result).toEqual({ packages: ['flask'] })
    })
  })

  describe('runBenchmarks', () => {
    it('calls benchmarks endpoint', async () => {
      apiClient.get.mockResolvedValue({
        data: { benchmarks: { score: 100 } }
      })

      const result = await systemService.runBenchmarks(true)

      expect(apiClient.get).toHaveBeenCalledWith('/system/benchmarks', {
        params: { comprehensive: true },
        timeout: 60000
      })
      expect(result).toEqual({ score: 100 })
    })
  })

  describe('getHealthStatus', () => {
    it('calls /health', async () => {
      apiClient.get.mockResolvedValue({
        data: { status: 'healthy' }
      })

      const result = await systemService.getHealthStatus()

      expect(apiClient.get).toHaveBeenCalledWith('/health')
      expect(result).toEqual({ status: 'healthy' })
    })
  })

  describe('formatSystemRequirements', () => {
    it('formats system info into requirement list', () => {
      const systemInfo = {
        gpu: { available: true, devices: [{ name: 'RTX 3080' }], cuda: '11.8', cudnn: '8.6', driver_version: '525' },
        runtime_versions: { python: { version: '3.11.0', location: '/usr/bin/python3' } },
        platform: { system: 'Linux', release: '6.2', platform: 'x86_64', machine: 'x86_64', version: '' },
        cpu: { brand: 'Intel Core i7', count: 4, logical_cores: 8, arch: 'x86_64' },
        memory: { total: 16000000000, available: 8000000000 }
      }

      const result = systemService.formatSystemRequirements(systemInfo)

      expect(result).toHaveLength(5)
      expect(result[0].type).toBe('gpu')
      expect(result[0].value).toBe('RTX 3080')
      expect(result[1].type).toBe('python')
      expect(result[3].type).toBe('cpu')
    })

    it('returns empty array for empty info', () => {
      expect(systemService.formatSystemRequirements({})).toEqual([])
    })
  })

  describe('compareSystemRequirements', () => {
    it('reports compatible when no requirements', () => {
      const result = systemService.compareSystemRequirements({}, {})
      expect(result.compatible).toBe(true)
      expect(result.issues).toEqual([])
    })

    it('detects missing GPU', () => {
      const result = systemService.compareSystemRequirements(
        {},
        { gpu: { cuda: '11.0' } }
      )
      expect(result.compatible).toBe(false)
      expect(result.issues).toContain('GPU required but not available')
    })

    it('detects insufficient CUDA version', () => {
      const systemInfo = { gpu: { available: true, cuda: '11.0', devices: [{ name: 'RTX 3080', memory: 10240 }] } }
      const result = systemService.compareSystemRequirements(
        systemInfo,
        { gpu: { cuda: '12.0' } }
      )
      expect(result.compatible).toBe(false)
      expect(result.issues[0]).toContain('CUDA 12.0')
    })

    it('detects missing Python', () => {
      const result = systemService.compareSystemRequirements(
        {},
        { python: '3.9' }
      )
      expect(result.compatible).toBe(false)
      expect(result.issues).toContain('Python not detected')
    })

    it('detects OS mismatch', () => {
      const systemInfo = { platform: { system: 'Windows' } }
      const result = systemService.compareSystemRequirements(
        systemInfo,
        { os: 'linux' }
      )
      expect(result.compatible).toBe(false)
      expect(result.issues[0]).toContain('linux')
    })
  })

  describe('checkVersionCompatibility', () => {
    it('returns compatible for matching version', () => {
      const result = systemService.checkVersionCompatibility('3.11.0', '3.9')
      expect(result.compatible).toBe(true)
    })

    it('returns incompatible for insufficient version', () => {
      const result = systemService.checkVersionCompatibility('3.8.0', '3.9')
      expect(result.compatible).toBe(false)
      expect(result.message).toContain('>=3.9')
    })

    it('checks max version constraint', () => {
      const result = systemService.checkVersionCompatibility('3.12.0', '3.9', '3.11')
      expect(result.compatible).toBe(false)
    })
  })

  describe('formatSystemInfo', () => {
    it('returns null for null input', () => {
      expect(systemService.formatSystemInfo(null)).toBeNull()
    })

    it('formats full system info', () => {
      const systemInfo = {
        platform: { system: 'Linux', release: '6.2', version: '', machine: 'x86_64', platform: 'x86_64' },
        cpu: { brand: 'Intel', count: 4, logical_cores: 8, arch: 'x86_64' },
        gpu: { available: false },
        memory: { total: 16000000000, available: 8000000000 },
        runtime_versions: { python: { version: '3.11.0', location: '/usr/bin/python3' } }
      }

      const result = systemService.formatSystemInfo(systemInfo)

      expect(result.os.name).toBe('Linux 6.2')
      expect(result.cpu.model).toBe('Intel')
      expect(result.memory.total).toBeTruthy()
      expect(result.python.version).toBe('3.11.0')
    })
  })

  describe('clearCache', () => {
    it('clears cached system info', async () => {
      apiClient.get.mockResolvedValue({
        data: { data: { platform: { system: 'Linux' } } }
      })

      await systemService.getSystemInfo()
      systemService.clearCache()
      await systemService.getSystemInfo()

      expect(apiClient.get).toHaveBeenCalledTimes(2)
    })
  })
})
