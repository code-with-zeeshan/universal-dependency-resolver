import { mount } from '@vue/test-utils'
import PackageSearch from '@/components/PackageSearch.vue'
import packageService from '@/services/packageService'

jest.mock('@/services/packageService')

beforeEach(() => {
  jest.clearAllMocks()
})

function createWrapper() {
  return mount(PackageSearch)
}

describe('PackageSearch', () => {
  it('renders search input and button', () => {
    const wrapper = createWrapper()
    expect(wrapper.find('input').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(true)
    expect(wrapper.find('select').exists()).toBe(true)
  })

  it('shows error when searching with empty query', async () => {
    const wrapper = createWrapper()
    const button = wrapper.find('button')
    await button.trigger('click')

    expect(wrapper.text()).toContain('Please enter a package name.')
  })

  it('calls searchPackages and displays results', async () => {
    const mockResults = [
      { name: 'flask', ecosystem: 'pypi', version: '2.3.3', description: 'A simple framework' }
    ]
    packageService.searchPackages.mockResolvedValue(mockResults)

    const wrapper = createWrapper()
    await wrapper.find('input').setValue('flask')
    await wrapper.find('button').trigger('click')

    await new Promise(process.nextTick)

    expect(packageService.searchPackages).toHaveBeenCalledWith(
      'flask', null, { flatten: true }
    )
    expect(wrapper.text()).toContain('flask')
    expect(wrapper.text()).toContain('pypi')
  })

  it('handles search errors gracefully', async () => {
    packageService.searchPackages.mockRejectedValue(new Error('API error'))

    const wrapper = createWrapper()
    await wrapper.find('input').setValue('flask')
    await wrapper.find('button').trigger('click')

    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('Failed to search packages')
  })

  it('emits package-selected when result is clicked', async () => {
    const mockResults = [
      { name: 'flask', ecosystem: 'pypi', version: '2.3.3' }
    ]
    packageService.searchPackages.mockResolvedValue(mockResults)

    const wrapper = createWrapper()
    await wrapper.find('input').setValue('flask')
    await wrapper.find('button').trigger('click')

    await new Promise(process.nextTick)

    const resultCard = wrapper.find('.info-card')
    await resultCard.trigger('click')

    expect(wrapper.emitted('package-selected')).toBeTruthy()
    expect(wrapper.emitted('package-selected')[0][0]).toEqual(mockResults[0])
  })

  it('filters by ecosystem when selected', async () => {
    packageService.searchPackages.mockResolvedValue([])

    const wrapper = createWrapper()
    await wrapper.find('input').setValue('flask')
    await wrapper.find('select').setValue('pypi')
    await wrapper.find('button').trigger('click')

    await new Promise(process.nextTick)

    expect(packageService.searchPackages).toHaveBeenCalledWith(
      'flask', ['pypi'], { flatten: true }
    )
  })

  it('shows no results message after empty search', async () => {
    packageService.searchPackages.mockResolvedValue([])

    const wrapper = createWrapper()
    await wrapper.find('input').setValue('react')
    await wrapper.find('button').trigger('click')

    await new Promise(process.nextTick)

    expect(wrapper.text()).toContain('No packages found')
  })
})
