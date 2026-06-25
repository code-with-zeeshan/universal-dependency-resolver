import packageService from '@/services/packageService'
import apiClient from '@/services/apiClient'

jest.mock('@/services/apiClient')

describe('packageService', () => {
  beforeEach(() => {
    jest.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    jest.clearAllMocks()
    console.error.mockRestore()
  })

  describe('searchPackages', () => {
    it('calls /packages/search with query params', async () => {
      const mockData = { results: { pypi: [{ name: 'flask' }] } }
      apiClient.get.mockResolvedValue({ data: mockData })

      const result = await packageService.searchPackages('flask', ['pypi'])

      expect(apiClient.get).toHaveBeenCalledWith('/packages/search', {
        params: { q: 'flask', ecosystems: 'pypi' }
      })
      expect(result).toEqual(mockData)
    })

    it('flattens results when option is set', async () => {
      apiClient.get.mockResolvedValue({
        data: { results: { pypi: [{ name: 'flask', version: '2.3' }] } }
      })

      const result = await packageService.searchPackages('flask', ['pypi'], { flatten: true })

      expect(result).toEqual([{ name: 'flask', version: '2.3', ecosystem: 'pypi' }])
    })

    it('throws on API error', async () => {
      apiClient.get.mockRejectedValue(new Error('Network error'))

      await expect(packageService.searchPackages('flask')).rejects.toThrow('Network error')
    })
  })

  describe('getPackageInfo', () => {
    it('calls /packages/{ecosystem}/{name}', async () => {
      apiClient.get.mockResolvedValue({ data: { name: 'flask' } })

      const result = await packageService.getPackageInfo('pypi', 'flask')

      expect(apiClient.get).toHaveBeenCalledWith('/packages/pypi/flask')
      expect(result).toEqual({ name: 'flask' })
    })
  })

  describe('getPackageVersions', () => {
    it('calls versions endpoint with options', async () => {
      apiClient.get.mockResolvedValue({ data: ['1.0', '2.0'] })

      const result = await packageService.getPackageVersions('pypi', 'flask', { include_prereleases: true })

      expect(apiClient.get).toHaveBeenCalledWith('/packages/pypi/flask/versions', {
        params: { include_prereleases: true }
      })
      expect(result).toEqual(['1.0', '2.0'])
    })
  })

  describe('getPackageDependencies', () => {
    it('calls dependencies endpoint', async () => {
      apiClient.get.mockResolvedValue({ data: { required: ['werkzeug'] } })

      const result = await packageService.getPackageDependencies('pypi', 'flask', '2.3.0', true)

      expect(apiClient.get).toHaveBeenCalledWith('/packages/pypi/flask/dependencies', {
        params: { version: '2.3.0', recursive: true }
      })
      expect(result).toEqual({ required: ['werkzeug'] })
    })
  })

  describe('getPackageCompatibility', () => {
    it('calls compatibility endpoint', async () => {
      apiClient.get.mockResolvedValue({ data: { compatible: true } })

      const result = await packageService.getPackageCompatibility('pypi', 'flask', '2.3.0')

      expect(apiClient.get).toHaveBeenCalledWith('/packages/pypi/flask/compatibility', {
        params: { version: '2.3.0' }
      })
      expect(result).toEqual({ compatible: true })
    })
  })

  describe('reportCompatibility', () => {
    it('posts compatibility report', async () => {
      apiClient.post.mockResolvedValue({ data: { success: true } })

      const result = await packageService.reportCompatibility('pypi', 'flask', '2.3.0', { os: 'linux' }, true, 'works fine')

      expect(apiClient.post).toHaveBeenCalledWith('/packages/pypi/flask/compatibility/report', {
        version: '2.3.0',
        system_info: { os: 'linux' },
        works: true,
        notes: 'works fine'
      })
      expect(result).toEqual({ success: true })
    })
  })

  describe('comparePackages', () => {
    it('calls compare endpoint', async () => {
      apiClient.get.mockResolvedValue({ data: { comparison: [] } })

      const result = await packageService.comparePackages(['flask', 'django'], 'all')

      expect(apiClient.get).toHaveBeenCalledWith('/packages/compare', {
        params: { packages: 'flask,django', aspects: 'all' }
      })
      expect(result).toEqual({ comparison: [] })
    })
  })

  describe('resolveDependencies', () => {
    it('posts packages and system info for resolution', async () => {
      apiClient.post.mockResolvedValue({ data: { status: 'success' } })

      const packages = [{ name: 'flask', ecosystem: 'pypi', version: '>=2.0' }]
      const systemInfo = { os: 'linux' }
      const result = await packageService.resolveDependencies(packages, systemInfo, {
        autoDetectSystem: false,
        preferCompatibility: true
      })

      expect(apiClient.post).toHaveBeenCalledWith('/packages/resolve', {
        packages: [{ name: 'flask', ecosystem: 'pypi', version: '>=2.0' }],
        system_info: { os: 'linux' },
        auto_detect_system: false,
        prefer_compatibility: true
      })
      expect(result).toEqual({ status: 'success' })
    })
  })

  describe('exportConfiguration', () => {
    it('posts resolved packages and format', async () => {
      apiClient.post.mockResolvedValue({ data: { content: 'flask==2.3.0' } })

      const result = await packageService.exportConfiguration(
        { flask: '2.3.0' }, 'requirements.txt', null, { pin_versions: true }
      )

      expect(apiClient.post).toHaveBeenCalledWith('/packages/export', {
        resolved_packages: { flask: '2.3.0' },
        format: 'requirements.txt',
        system_info: null,
        options: { pin_versions: true }
      })
      expect(result).toEqual({ content: 'flask==2.3.0' })
    })
  })

  describe('getExportFormats', () => {
    it('calls export-formats endpoint', async () => {
      apiClient.get.mockResolvedValue({ data: ['requirements.txt', 'package.json'] })

      const result = await packageService.getExportFormats()

      expect(apiClient.get).toHaveBeenCalledWith('/packages/export-formats')
      expect(result).toEqual(['requirements.txt', 'package.json'])
    })
  })
})
