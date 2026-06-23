import { mount } from '@vue/test-utils'
import SystemInfo from '@/components/SystemInfo.vue'
import systemService from '@/services/systemService'

jest.mock('@/services/systemService')

beforeEach(() => {
  jest.clearAllMocks()
})

const stubs = {
  RefreshIcon: { template: '<span>RefreshIcon</span>' },
  ComputerIcon: { template: '<span>ComputerIcon</span>' },
  CpuIcon: { template: '<span>CpuIcon</span>' },
  GpuIcon: { template: '<span>GpuIcon</span>' },
  CodeIcon: { template: '<span>CodeIcon</span>' }
}

function createWrapper() {
  return mount(SystemInfo, {
    global: { stubs }
  })
}

describe('SystemInfo', () => {
  it('renders the system info section', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('System Information')
  })

  it('displays system data after loading', async () => {
    systemService.getSystemInfo.mockResolvedValue({
      os: { system: 'Linux', release: '6.2', machine: 'x86_64' },
      cpu: { brand: 'Intel Core i7', count: 4, count_logical: 8, arch: 'x86_64' },
      gpu: { available: false },
      memory: { total: 16000000000, available: 8000000000 },
      runtime_versions: { python: { version: '3.11.0' } }
    })

    const wrapper = createWrapper()
    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('Linux')
    expect(wrapper.text()).toContain('Intel Core i7')
    expect(wrapper.text()).toContain('3.11.0')

    const refreshButton = wrapper.find('.refresh-button')
    expect(refreshButton.exists()).toBe(true)
  })

  it('calls getSystemInfo on mount', () => {
    systemService.getSystemInfo.mockResolvedValue({ os: { system: 'Linux' } })
    createWrapper()
    expect(systemService.getSystemInfo).toHaveBeenCalled()
  })

  it('refreshes data when refresh button is clicked', async () => {
    systemService.getSystemInfo.mockResolvedValue({ os: { system: 'Linux' } })
    const wrapper = createWrapper()

    await new Promise(process.nextTick)

    systemService.getSystemInfo.mockResolvedValue({ os: { system: 'macOS' } })
    await wrapper.find('.refresh-button').trigger('click')

    await new Promise(process.nextTick)

    expect(systemService.getSystemInfo).toHaveBeenCalledTimes(2)
  })

  it('handles load errors gracefully', async () => {
    systemService.getSystemInfo.mockRejectedValue(new Error('API error'))
    const wrapper = createWrapper()

    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('System information not yet loaded')
  })

  it('formats GPU memory correctly', async () => {
    systemService.getSystemInfo.mockResolvedValue({
      os: { system: 'Linux', release: '6.2', machine: 'x86_64' },
      gpu: { available: true, devices: [{ name: 'RTX 3080', memory_mb: 10240, memory_total: 10240, memory_free: 5120 }], cuda: '11.8' },
      memory: { total: 16000000000, available: 8000000000 }
    })

    const wrapper = createWrapper()
    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('RTX 3080')
    expect(wrapper.text()).toContain('11.8')
  })

  it('shows GPU unavailable state', async () => {
    systemService.getSystemInfo.mockResolvedValue({
      os: { system: 'Linux', release: '6.2', machine: 'x86_64' },
      gpu: { available: false }
    })

    const wrapper = createWrapper()
    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('No GPU detected')
  })
})
