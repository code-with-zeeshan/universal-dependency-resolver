import { mount } from '@vue/test-utils'
import ResolvePanel from '@/components/ResolvePanel.vue'
import packageService from '@/services/packageService'
import systemService from '@/services/systemService'

jest.mock('@/services/packageService')
jest.mock('@/services/systemService')

beforeEach(() => {
  jest.clearAllMocks()
  packageService.getExportFormats.mockResolvedValue({ formats: ['requirements.txt', 'package.json'] })
})

function createWrapper() {
  return mount(ResolvePanel, {
    global: {
      stubs: {
        SystemInfo: { template: '<div class="system-info-stub"><slot /></div>' },
        PlusIcon: { template: '<span>PlusIcon</span>' },
        XMarkIcon: { template: '<span>XMarkIcon</span>' },
        ArrowDownTrayIcon: { template: '<span>ArrowDownTrayIcon</span>' },
        ClipboardDocumentIcon: { template: '<span>ClipboardDocumentIcon</span>' },
        CheckBadgeIcon: { template: '<span>CheckBadgeIcon</span>' },
      }
    }
  })
}

describe('ResolvePanel', () => {
  it('renders the panel', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('Dependency Resolution')
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
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      expect(wrapper.text()).toContain('flask')
    })

    it('shows error when adding empty package', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      expect(wrapper.text()).toContain('Package name is required.')
    })

    it('removes a package from the list', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      expect(wrapper.text()).toContain('flask')
      const removeBtn = wrapper.findAll('button').filter(b => b.text() === 'Remove').pop()
      if (removeBtn) await removeBtn.trigger('click')
      await wrapper.vm.$nextTick()
      expect(wrapper.text()).not.toContain('flask')
    })

    it('selects ecosystem when adding package', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      const ecosystemSelect = wrapper.find('.form-select')
      await ecosystemSelect.setValue('pypi')
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      expect(wrapper.text()).toContain('pypi')
    })
  })

  describe('dependency resolution', () => {
    it('shows error when resolving with no packages', async () => {
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const resolveBtn = wrapper.findAll('button').filter(b => b.text() === 'Resolve Dependencies').pop()
      await resolveBtn.trigger('click')
      expect(wrapper.text()).toContain('No packages selected.')
    })

    it('resolves dependencies when button is clicked', async () => {
      packageService.resolveDependencies.mockResolvedValue({
        status: 'success',
        resolved_packages: { flask: { version: '2.3.3', ecosystem: 'pypi' } }
      })
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      const ecosystemSelect = wrapper.find('.form-select')
      await ecosystemSelect.setValue('pypi')
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      await wrapper.vm.$nextTick()
      const resolveBtn = wrapper.findAll('button').filter(b => b.text() === 'Resolve Dependencies').pop()
      await resolveBtn.trigger('click')
      await new Promise(process.nextTick)
      expect(wrapper.text()).toContain('Resolved Dependencies')
    })

    it('handles resolution failure', async () => {
      packageService.resolveDependencies.mockRejectedValue(new Error('Resolution failed'))
      const wrapper = createWrapper()
      await new Promise(process.nextTick)
      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      await wrapper.vm.$nextTick()
      const resolveBtn = wrapper.findAll('button').filter(b => b.text() === 'Resolve Dependencies').pop()
      await resolveBtn.trigger('click')
      await new Promise(process.nextTick)
      expect(wrapper.text()).toContain('Failed to resolve dependencies')
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
      const nameInput = wrapper.find('.form-input')
      await nameInput.setValue('flask')
      const addBtn = wrapper.findAll('button').filter(b => b.text() === 'Add').pop()
      await addBtn.trigger('click')
      await wrapper.vm.$nextTick()
      const resolveBtn = wrapper.findAll('button').filter(b => b.text() === 'Resolve Dependencies').pop()
      await resolveBtn.trigger('click')
      await new Promise(process.nextTick)
      expect(wrapper.text()).toContain('requirements.txt')
      expect(wrapper.text()).toContain('package.json')
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
    it('clears success message after 2 seconds', async () => {
      jest.useFakeTimers()
      const wrapper = createWrapper()
      wrapper.vm.exportPreview = { format: 'txt', content: 'test' }
      await wrapper.vm.copyToClipboard()
      expect(wrapper.vm.successMessage).toBe('Copied to clipboard!')
      jest.advanceTimersByTime(2000)
      expect(wrapper.vm.successMessage).toBeNull()
      jest.useRealTimers()
    })
  })
})
