const { describe, it } = require('node:test')
const assert = require('node:assert')

// Workaround: global sessionStorage for app-utils.js cacheLastLock
if (typeof globalThis.sessionStorage === 'undefined') {
  const store = {}
  globalThis.sessionStorage = {
    getItem: (k) => store[k] || null,
    setItem: (k, v) => { store[k] = String(v) },
    removeItem: (k) => { delete store[k] },
    clear: () => { Object.keys(store).forEach(k => delete store[k]) },
  }
}

const {
  formatResolveTable,
  formatSearchResults,
  formatVersions,
  formatDependencies,
  formatCompatibility,
  formatScanResult,
  formatGraphTree,
  formatVerifyResult,
  formatUpdateResult,
  cacheLastLock,
} = require('../app-utils')

describe('app-utils formatting', () => {
  describe('formatResolveTable', () => {
    it('shows empty warning for no packages', () => {
      const html = formatResolveTable({ resolved_packages: {} })
      assert.match(html, /No packages resolved/)
    })

    it('renders a table with packages', () => {
      const html = formatResolveTable({
        resolved_packages: {
          requests: { version: '2.31.0', ecosystem: 'pypi' },
          torch: { version: '2.3.0', ecosystem: 'pypi', cuda_version: '12.1' },
        },
        status: 'satisfiable',
      })
      assert.match(html, /requests/)
      assert.match(html, /torch/)
      assert.match(html, /All dependencies resolved successfully/)
      assert.match(html, /CUDA 12\.1/)
    })

    it('shows unsatisfiable warning', () => {
      const html = formatResolveTable({
        resolved_packages: { bad: { version: '1.0', ecosystem: 'pypi' } },
        status: 'unsatisfiable',
      })
      assert.match(html, /could not be satisfied/)
    })

    it('includes warnings section', () => {
      const html = formatResolveTable({
        resolved_packages: { a: { version: '1.0', ecosystem: 'pypi' } },
        status: 'satisfiable',
        warnings: ['Deprecated package a'],
      })
      assert.match(html, /Deprecated package a/)
    })
  })

  describe('formatSearchResults', () => {
    it('shows empty warning for no results', () => {
      const html = formatSearchResults({ results: {} })
      assert.match(html, /No results found/)
    })

    it('renders results grouped by ecosystem', () => {
      const html = formatSearchResults({
        results: {
          pypi: [{ name: 'flask', version: '3.0.0', description: 'A micro framework' }],
        },
        total_count: 1,
      })
      assert.match(html, /flask/)
      assert.match(html, /pypi/)
      assert.match(html, /A micro framework/)
    })
  })

  describe('formatVersions', () => {
    it('shows warning when no versions', () => {
      const html = formatVersions({ versions: { pypi: [] } })
      assert.match(html, /No versions found/)
    })

    it('renders version table', () => {
      const html = formatVersions({
        data: {
          versions: {
            pypi: [
              { version: '1.0.0', release_date: '2024-01-01', python_requires: '>=3.8' },
              { version: '0.9.0' },
            ],
          },
        },
      })
      assert.match(html, /1\.0\.0/)
      assert.match(html, /0\.9\.0/)
      assert.match(html, /2 versions available/)
    })

    it('handles string-only versions', () => {
      const html = formatVersions({
        data: {
          ecosystem: 'pypi',
          versions: { pypi: ['1.0.0', '2.0.0'] },
        },
      })
      assert.match(html, /1\.0\.0/)
      assert.match(html, /2\.0\.0/)
    })
  })

  describe('formatDependencies', () => {
    it('shows warning when no deps', () => {
      const html = formatDependencies({ dependencies: { pypi: { all: [] } } }, 'pypi')
      assert.match(html, /No dependencies found/)
    })

    it('renders dependency table', () => {
      const html = formatDependencies({
        dependencies: {
          npm: {
            all: [
              { name: 'react', version_spec: '^18.0.0', optional: false },
              { name: 'lodash', requirement: '^4.0.0', optional: true },
            ],
          },
        },
      }, 'npm')
      assert.match(html, /react/)
      assert.match(html, /lodash/)
      assert.match(html, /\^18\.0\.0/)
    })
  })

  describe('formatCompatibility', () => {
    it('shows warning when empty', () => {
      const html = formatCompatibility({})
      assert.match(html, /No compatibility information available/)
    })

    it('renders compatibility table', () => {
      const html = formatCompatibility({
        compatibility_matrix: {
          'python>=3.8': { compatible: true, note: 'OK' },
          'torch<=2.0': { compatible: false, message: 'Incompatible' },
        },
      })
      assert.match(html, /Compatible/)
      assert.match(html, /Incompatible/)
    })
  })

  describe('formatScanResult', () => {
    it('shows no_manifests message', () => {
      const html = formatScanResult({ status: 'no_manifests' })
      assert.match(html, /No manifest files found/)
    })

    it('shows no_packages message', () => {
      const html = formatScanResult({ status: 'no_packages' })
      assert.match(html, /No packages found/)
    })

    it('renders manifests and packages', () => {
      const html = formatScanResult({
        status: 'success',
        manifests: [{ filename: 'requirements.txt', ecosystem: 'pypi' }],
        packages: [{ name: 'flask', ecosystem: 'pypi', constraint: '>=3.0', resolved_version: '3.0.0' }],
        system: { os: 'Linux', python: '3.12' },
      })
      assert.match(html, /requirements\.txt/)
      assert.match(html, /flask/)
      assert.match(html, /Linux/)
      assert.match(html, /3\.12/)
    })
  })

  describe('formatGraphTree', () => {
    it('shows warning when empty', () => {
      const html = formatGraphTree([])
      assert.match(html, /No dependency tree available/)
    })

    it('renders a tree', () => {
      const html = formatGraphTree([
        {
          name: 'flask',
          version: '3.0.0',
          ecosystem: 'pypi',
          children: [
            { name: 'werkzeug', version: '3.0.0', ecosystem: 'pypi', children: [] },
          ],
        },
      ])
      assert.match(html, /flask/)
      assert.match(html, /werkzeug/)
    })
  })

  describe('formatVerifyResult', () => {
    it('shows success when no issues', () => {
      const html = formatVerifyResult({ total: 5, ok: 5, issues: [] })
      assert.match(html, /5\/5 packages verified successfully/)
    })

    it('lists error issues', () => {
      const html = formatVerifyResult({
        total: 2, ok: 0,
        issues: [
          { severity: 'error', name: 'bad-pkg', issue: 'Version not found' },
          { severity: 'warning', name: 'old-pkg', issue: 'Deprecated' },
        ],
      })
      assert.match(html, /0\/2/)
      assert.match(html, /ERROR/)
      assert.match(html, /bad-pkg/)
      assert.match(html, /WARN/)
      assert.match(html, /old-pkg/)
    })
  })

  describe('formatUpdateResult', () => {
    it('shows updated message', () => {
      const html = formatUpdateResult({ updated: true, package: 'flask', old_version: '2.0', new_version: '3.0' })
      assert.match(html, /flask/)
      assert.match(html, /updated/)
      assert.match(html, /2\.0/)
      assert.match(html, /3\.0/)
    })

    it('shows no-update message', () => {
      const html = formatUpdateResult({ updated: false, package: 'click', old_version: '8.1', new_version: '8.1' })
      assert.match(html, /click/)
      assert.match(html, /already at/)
    })
  })

  describe('cacheLastLock', () => {
    it('stores lock data in sessionStorage', () => {
      const lockData = { packages: { requests: { version: '2.31.0' } } }
      cacheLastLock(lockData)
      const stored = sessionStorage.getItem('udr_lastLock')
      assert.ok(stored)
      const parsed = JSON.parse(stored)
      assert.equal(parsed.packages.requests.version, '2.31.0')
    })

    it('does not throw on sessionStorage error', () => {
      const origSetItem = globalThis.sessionStorage.setItem
      globalThis.sessionStorage.setItem = () => { throw new Error('full') }
      cacheLastLock({ data: 'test' })
      globalThis.sessionStorage.setItem = origSetItem
    })
  })
})
