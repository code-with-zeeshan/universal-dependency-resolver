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
  DashboardPanel: { template: '<div class="panel-stub">Dashboard</div>' },
  PackagePanel: { template: '<div class="panel-stub">Packages</div>' },
  ResolvePanel: { template: '<div class="panel-stub">Resolve</div>' },
  SystemPanel: { template: '<div class="panel-stub">System</div>' },
  AuthPanel: { template: '<div class="panel-stub">Auth</div>' },
  HomeIcon: { template: '<span>HomeIcon</span>' },
  MagnifyingGlassIcon: { template: '<span>MagnifyingGlassIcon</span>' },
  CheckBadgeIcon: { template: '<span>CheckBadgeIcon</span>' },
  ServerIcon: { template: '<span>ServerIcon</span>' },
  LockClosedIcon: { template: '<span>LockClosedIcon</span>' },
}

function createWrapper() {
  return mount(App, {
    global: { stubs }
  })
}

describe('App', () => {
  it('renders sidebar with navigation items', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('UDR')
    expect(wrapper.text()).toContain('Dashboard')
    expect(wrapper.text()).toContain('Packages')
    expect(wrapper.text()).toContain('Resolve')
    expect(wrapper.text()).toContain('System')
    expect(wrapper.text()).toContain('Auth')
  })

  it('shows Dashboard panel by default', () => {
    const wrapper = createWrapper()
    expect(wrapper.text()).toContain('Dashboard')
  })

  it('switches to Packages panel when Packages nav is clicked', async () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('button')
    const packagesBtn = buttons.find(b => b.text().includes('Packages'))
    await packagesBtn.trigger('click')
    expect(wrapper.text()).toContain('Packages')
    expect(wrapper.text()).not.toContain('Dashboard')
  })

  it('switches to Resolve panel when Resolve nav is clicked', async () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('button')
    const resolveBtn = buttons.find(b => b.text().includes('Resolve'))
    await resolveBtn.trigger('click')
    expect(wrapper.text()).toContain('Resolve')
  })

  it('switches to System panel when System nav is clicked', async () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('button')
    const resolveBtn = buttons.find(b => b.text().includes('System'))
    await resolveBtn.trigger('click')
    expect(wrapper.text()).toContain('System')
  })

  it('switches to Auth panel when Auth nav is clicked', async () => {
    const wrapper = createWrapper()
    const buttons = wrapper.findAll('button')
    const authBtn = buttons.find(b => b.text().includes('Auth'))
    await authBtn.trigger('click')
    expect(wrapper.text()).toContain('Auth')
  })

  it('navigates to Resolve when DashboardPanel emits navigate event', async () => {
    const wrapper = createWrapper()
    const dashboard = wrapper.findComponent({ name: 'DashboardPanel' })
    dashboard.vm.$emit('navigate', 'resolve')
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Resolve')
  })
})
