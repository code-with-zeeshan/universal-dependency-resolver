import { mount } from '@vue/test-utils'
import App from '@/App.vue'
import packageService from '@/services/packageService'
import systemService from '@/services/systemService'

jest.mock('@/services/packageService')
jest.mock('@/services/systemService')

beforeEach(() => {
  jest.clearAllMocks()
  packageService.getExportFormats.mockResolvedValue(['requirements.txt', 'package.json'])
})

const stubs = {
  SystemInfo: { template: '<div class="system-info-stub"><slot /></div>' },
  RefreshIcon: { template: '<span>RefreshIcon</span>' },
  ComputerIcon: { template: '<span>ComputerIcon</span>' },
  CpuIcon: { template: '<span>CpuIcon</span>' },
  GpuIcon: { template: '<span>GpuIcon</span>' },
  CodeIcon: { template: '<span>CodeIcon</span>' }
}

function createWrapper() {
  return mount(App, {
    global: { stubs }
  })
}

describe('App', () => {
  it('renders the app title', async () => {
    const wrapper = createWrapper()
    await new Promise(process.nextTick)
    expect(wrapper.text()).toContain('Universal Dependency Resolver')
  })

  it('loads export formats on mount', async () => {
    createWrapper()
    await new Promise(process.nextTick)
    expect(packageService.getExportFormats).toHaveBeenCalled()
  })

  it('handles export format load error', async () => {
    packageService.getExportFormats.mockRejectedValue(new Error('API error'))
    const wrapper = createWrapper()
    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('Failed to load export formats')
  })

  describe('package management', () => {
    it('adds a package to the list', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      await wrapper.vm.addPackage()

      expect(wrapper.text()).toContain('flask')
    })

    it('shows error when adding empty package', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = ''
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()

      expect(wrapper.text()).toContain('Package name is required.')
    })

    it('removes a package from the list', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()
      expect(wrapper.text()).toContain('flask')
      expect(wrapper.text()).toContain('(')

      wrapper.vm.removePackage(0)
      await wrapper.vm.$nextTick()
      await wrapper.vm.$nextTick()
      expect(wrapper.text()).not.toContain('flask')
    })

    it('selects ecosystem when adding package', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.newPackage.ecosystem = 'pypi'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()

      expect(wrapper.text()).toContain('pypi')
    })
  })

  describe('dependency resolution', () => {
    it('shows error when resolving with no packages', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      await wrapper.vm.resolveDependencies()

      expect(wrapper.vm.errorMessage).toBe('No packages selected.')
      expect(wrapper.text()).toContain('No packages selected.')
    })

    it('resolves dependencies when button is clicked', async () => {
      packageService.resolveDependencies.mockResolvedValue({
        status: 'success',
        resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } }
      })

      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()

      await wrapper.vm.resolveDependencies()
      await new Promise(process.nextTick)

      expect(wrapper.text()).toContain('Resolved Dependencies')
    })

    it('handles resolution failure', async () => {
      packageService.resolveDependencies.mockRejectedValue(new Error('Resolution failed'))

      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()

      await wrapper.vm.resolveDependencies()
      await new Promise(process.nextTick)

      expect(wrapper.text()).toContain('Failed to resolve dependencies')
    })

    it('shows resolve button as disabled when no packages', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      const resolveBtn = wrapper.findAll('button').filter(b => b.text() === 'Resolve Dependencies')
      if (resolveBtn.length) {
        expect(resolveBtn[0].element.disabled).toBe(true)
      }
    })
  })

  describe('export', () => {
    it('shows export formats after resolution', async () => {
      packageService.resolveDependencies.mockResolvedValue({
        status: 'success',
        resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } }
      })

      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()
      await wrapper.vm.resolveDependencies()
      await new Promise(process.nextTick)

      expect(wrapper.text()).toContain('requirements.txt')
      expect(wrapper.text()).toContain('package.json')
    })

    it('calls exportConfiguration when export button clicked', async () => {
      packageService.resolveDependencies.mockResolvedValue({
        status: 'success',
        resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } }
      })
      packageService.exportConfiguration.mockResolvedValue({
        content: 'flask==2.3.3'
      })

      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.newPackage.name = 'flask'
      wrapper.vm.addPackage()
      await wrapper.vm.$nextTick()
      await wrapper.vm.resolveDependencies()
      await new Promise(process.nextTick)

      await wrapper.vm.exportConfig('requirements.txt')

      expect(packageService.exportConfiguration).toHaveBeenCalled()
    })
  })

  describe('system info updates', () => {
    it('updates system info when SystemInfo emits event', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      const sysInfo = { os: { system: 'Linux' } }
      wrapper.vm.updateSystemInfo(sysInfo)
      expect(wrapper.vm.systemInfo).toEqual(sysInfo)
    })
  })

  describe('clipboard', () => {
    beforeEach(() => {
      Object.assign(navigator, {
        clipboard: { writeText: jest.fn().mockResolvedValue(undefined) }
      })
    })

    it('copies export preview to clipboard', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      wrapper.vm.exportPreview = { format: 'requirements.txt', content: 'flask==2.3.3' }
      await wrapper.vm.copyToClipboard()

      expect(navigator.clipboard.writeText).toHaveBeenCalledWith('flask==2.3.3')
    })

    it('does nothing when no export preview', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)

      await wrapper.vm.copyToClipboard()
      expect(navigator.clipboard.writeText).not.toHaveBeenCalled()
    })
  })

  describe('download', () => {
    it('creates a blob URL and triggers download', () => {
      const createObjectURL = jest.fn(() => 'blob:test')
      const revokeObjectURL = jest.fn()
      window.URL.createObjectURL = createObjectURL
      window.URL.revokeObjectURL = revokeObjectURL

      const wrapper = createWrapper()
      wrapper.vm.exportPreview = { format: 'requirements.txt', content: 'flask==2.3.3' }

      wrapper.vm.downloadFile()

      expect(createObjectURL).toHaveBeenCalled()
      expect(revokeObjectURL).toHaveBeenCalled()
    })

    it('does nothing when no export preview', () => {
      const createObjectURL = jest.fn()
      window.URL.createObjectURL = createObjectURL

      const wrapper = createWrapper()
      wrapper.vm.downloadFile()

      expect(createObjectURL).not.toHaveBeenCalled()
    })
  })

  describe('error handling', () => {
    it('clears error message after 2 seconds', async () => {
      jest.useFakeTimers()

      const wrapper = createWrapper()
      wrapper.vm.exportPreview = { format: 'txt', content: 'test' }
      await wrapper.vm.copyToClipboard()

      expect(wrapper.vm.errorMessage).toBe('Copied to clipboard!')

      jest.advanceTimersByTime(2000)
      expect(wrapper.vm.errorMessage).toBeNull()

      jest.useRealTimers()
    })
  })
})
