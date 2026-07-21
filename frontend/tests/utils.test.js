describe('escapeHtml', () => {
  test('escapes angle brackets and ampersands', () => {
    const result = Utils.escapeHtml('<script>alert("xss")</script>');
    expect(result).toContain('&lt;script&gt;');
    expect(result).toContain('&lt;/script&gt;');
    expect(result).not.toContain('<');
  });

  test('escapes ampersands', () => {
    expect(Utils.escapeHtml('a & b')).toBe('a &amp; b');
  });

  test('returns empty string for empty input', () => {
    expect(Utils.escapeHtml('')).toBe('');
  });

  test('handles strings without special characters', () => {
    expect(Utils.escapeHtml('hello world')).toBe('hello world');
  });

  test('handles null/undefined gracefully', () => {
    expect(Utils.escapeHtml(null)).toBe('');
    expect(Utils.escapeHtml(undefined)).toBe('');
  });
});

describe('plural', () => {
  test('returns singular for n === 1', () => {
    expect(Utils.plural(1, 'package')).toBe('package');
  });

  test('returns plural for n === 0', () => {
    expect(Utils.plural(0, 'package')).toBe('packages');
  });

  test('returns plural for n > 1', () => {
    expect(Utils.plural(5, 'package')).toBe('packages');
  });
});

describe('formatDate', () => {
  test('formats valid ISO date', () => {
    const result = Utils.formatDate('2024-01-15T10:30:00Z');
    expect(result).not.toBe('—');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });

  test('returns em dash for null/undefined', () => {
    expect(Utils.formatDate(null)).toBe('—');
    expect(Utils.formatDate(undefined)).toBe('—');
  });

  test('returns formatted string for invalid date (no throw)', () => {
    const result = Utils.formatDate('not-a-date');
    expect(typeof result).toBe('string');
    expect(result.length).toBeGreaterThan(0);
  });
});

describe('timeAgo', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date('2024-06-15T12:00:00Z'));
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('returns "just now" for less than 1 minute ago', () => {
    const iso = new Date('2024-06-15T11:59:45Z').toISOString();
    expect(Utils.timeAgo(iso)).toBe('just now');
  });

  test('returns minutes ago', () => {
    const iso = new Date('2024-06-15T11:55:00Z').toISOString();
    expect(Utils.timeAgo(iso)).toBe('5m ago');
  });

  test('returns hours ago', () => {
    const iso = new Date('2024-06-15T09:00:00Z').toISOString();
    expect(Utils.timeAgo(iso)).toBe('3h ago');
  });

  test('returns days ago', () => {
    const iso = new Date('2024-06-10T12:00:00Z').toISOString();
    expect(Utils.timeAgo(iso)).toBe('5d ago');
  });

  test('returns em dash for null/undefined', () => {
    expect(Utils.timeAgo(null)).toBe('—');
    expect(Utils.timeAgo(undefined)).toBe('—');
  });
});

describe('truncate', () => {
  test('returns string as-is when shorter than limit', () => {
    expect(Utils.truncate('short', 60)).toBe('short');
  });

  test('returns string as-is when equal to limit', () => {
    const str = 'a'.repeat(60);
    expect(Utils.truncate(str, 60)).toBe(str);
  });

  test('truncates string longer than limit with ellipsis', () => {
    const result = Utils.truncate('a'.repeat(100), 60);
    expect(result).toBe('a'.repeat(60) + '\u2026');
    expect(result.length).toBe(61);
  });

  test('uses default limit of 60', () => {
    expect(Utils.truncate('a'.repeat(100)).length).toBe(61);
  });

  test('returns null/undefined as-is', () => {
    expect(Utils.truncate(null)).toBeNull();
    expect(Utils.truncate(undefined)).toBeUndefined();
  });

  test('returns empty string as-is', () => {
    expect(Utils.truncate('')).toBe('');
  });
});

describe('severityClass', () => {
  test('returns "critical" for critical', () => {
    expect(Utils.severityClass('critical')).toBe('critical');
    expect(Utils.severityClass('CRITICAL')).toBe('critical');
    expect(Utils.severityClass('Critical')).toBe('critical');
  });

  test('returns "high" for high', () => {
    expect(Utils.severityClass('high')).toBe('high');
  });

  test('returns "moderate" for moderate or medium', () => {
    expect(Utils.severityClass('moderate')).toBe('moderate');
    expect(Utils.severityClass('medium')).toBe('moderate');
  });

  test('returns "low" for low', () => {
    expect(Utils.severityClass('low')).toBe('low');
  });

  test('returns "error" for error', () => {
    expect(Utils.severityClass('error')).toBe('error');
  });

  test('returns "warning" for warning', () => {
    expect(Utils.severityClass('warning')).toBe('warning');
  });

  test('returns "ok" for ok or pass', () => {
    expect(Utils.severityClass('ok')).toBe('ok');
    expect(Utils.severityClass('pass')).toBe('ok');
  });

  test('returns "low" for null/undefined/unknown', () => {
    expect(Utils.severityClass(null)).toBe('low');
    expect(Utils.severityClass(undefined)).toBe('low');
    expect(Utils.severityClass('unknown')).toBe('low');
  });
});

describe('severityBadge', () => {
  test('returns HTML span with correct class and text', () => {
    const result = Utils.severityBadge('critical');
    expect(result).toContain('<span class="severity critical">');
    expect(result).toContain('critical');
  });

  test('escapes text in badge', () => {
    const result = Utils.severityBadge('<danger>');
    expect(result).toContain('&lt;danger&gt;');
  });
});

describe('ecoColor', () => {
  test('returns correct color for known ecosystems', () => {
    expect(Utils.ecoColor('pypi')).toBe('#3775a9');
    expect(Utils.ecoColor('npm')).toBe('#cb3837');
    expect(Utils.ecoColor('crates')).toBe('#f7df1e');
    expect(Utils.ecoColor('maven')).toBe('#c71a36');
    expect(Utils.ecoColor('nuget')).toBe('#004880');
  });

  test('returns fallback for unknown ecosystem', () => {
    expect(Utils.ecoColor('unknown')).toBe('var(--text-muted)');
  });
});

describe('ecoBadge', () => {
  test('returns HTML span with ecosystem name', () => {
    const result = Utils.ecoBadge('pypi');
    expect(result).toContain('<span class="eco-badge"');
    expect(result).toContain('pypi');
    expect(result).toContain('#3775a9');
  });

  test('escapes ecosystem name', () => {
    const result = Utils.ecoBadge('<test>');
    expect(result).toContain('&lt;test&gt;');
  });
});

describe('parseLockFile', () => {
  test('parses valid JSON', () => {
    const data = Utils.parseLockFile('{"packages": {"a": {}}}');
    expect(data).toEqual({ packages: { a: {} } });
  });

  test('throws error for invalid JSON', () => {
    expect(() => Utils.parseLockFile('not json')).toThrow('Invalid JSON in lock file');
  });
});

describe('getPackagesFromLock', () => {
  test('returns "packages" key when present', () => {
    const result = Utils.getPackagesFromLock({ packages: { a: {} } });
    expect(result).toEqual({ a: {} });
  });

  test('returns "resolved_packages" when "packages" absent', () => {
    const result = Utils.getPackagesFromLock({ resolved_packages: { b: {} } });
    expect(result).toEqual({ b: {} });
  });

  test('returns empty object when no packages key', () => {
    expect(Utils.getPackagesFromLock({ metadata: {} })).toEqual({});
  });

  test('returns empty object for null/undefined', () => {
    expect(Utils.getPackagesFromLock(null)).toEqual({});
    expect(Utils.getPackagesFromLock(undefined)).toEqual({});
  });
});

describe('getPackageCount', () => {
  test('returns count of packages', () => {
    const data = { packages: { a: {}, b: {}, c: {} } };
    expect(Utils.getPackageCount(data)).toBe(3);
  });

  test('returns 0 when no packages', () => {
    expect(Utils.getPackageCount({})).toBe(0);
    expect(Utils.getPackageCount(null)).toBe(0);
  });
});

describe('makeSpinner', () => {
  test('creates a loading overlay div', () => {
    const spinner = Utils.makeSpinner();
    expect(spinner.className).toBe('loading-overlay');
    expect(spinner.innerHTML).toContain('spinner');
    expect(spinner.innerHTML).toContain('Loading...');
  });
});

describe('makeToast', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="toast-container"></div>';
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  test('creates a toast element in the container', () => {
    Utils.makeToast('Test message', 'success');
    const toast = document.querySelector('.toast');
    expect(toast).toBeTruthy();
    expect(toast.className).toBe('toast success');
    expect(toast.textContent).toContain('Test message');
  });

  test('uses correct icon for type', () => {
    Utils.makeToast('Error!', 'error');
    const toast = document.querySelector('.toast');
    expect(toast.textContent).toContain('\u2717');
  });

  test('uses info icon for default type', () => {
    Utils.makeToast('Info');
    const toast = document.querySelector('.toast');
    expect(toast.textContent).toContain('\u2139');
  });

  test('removes toast after animation timeout', () => {
    Utils.makeToast('Auto remove', 'info');
    expect(document.querySelector('.toast')).toBeTruthy();

    jest.advanceTimersByTime(4000);
    expect(document.querySelector('.toast').style.opacity).toBe('0');

    jest.advanceTimersByTime(300);
    expect(document.querySelector('.toast')).toBeFalsy();
  });

});

describe('checkLicenses', () => {
  const packages = {
    'pkg-a': { license: 'MIT', ecosystem: 'pypi', resolved_version: '1.0.0' },
    'pkg-b': { license: 'GPL-3.0-only', ecosystem: 'npm', resolved_version: '2.0.0' },
    'pkg-c': { license: 'AGPL-3.0-or-later', ecosystem: 'crates', resolved_version: '3.0.0' },
    'pkg-d': { license: 'LGPL-2.1-only', ecosystem: 'rubygems', resolved_version: '4.0.0' },
    'pkg-e': { license: 'Unknown', ecosystem: 'nuget', resolved_version: '5.0.0' },
    'pkg-f': { ecosystem: 'pypi', resolved_version: '6.0.0' },
    'pkg-g': { license: 'Apache-2.0', ecosystem: 'maven', resolved_version: '7.0.0' },
  };

  test('marks permissive licenses as approved', () => {
    const results = Utils.checkLicenses(packages);
    expect(results.find(r => r.package === 'pkg-a').status).toBe('approved');
    expect(results.find(r => r.package === 'pkg-g').status).toBe('approved');
  });

  test('marks GPL/AGPL/LGPL as restricted', () => {
    const results = Utils.checkLicenses(packages);
    expect(results.find(r => r.package === 'pkg-b').status).toBe('restricted');
    expect(results.find(r => r.package === 'pkg-c').status).toBe('restricted');
    expect(results.find(r => r.package === 'pkg-d').status).toBe('restricted');
  });

  test('marks unknown license as unknown', () => {
    const results = Utils.checkLicenses(packages);
    expect(results.find(r => r.package === 'pkg-e').status).toBe('unknown');
  });

  test('handles package with no license field', () => {
    const results = Utils.checkLicenses(packages);
    expect(results.find(r => r.package === 'pkg-f').license).toBe('Unknown');
    expect(results.find(r => r.package === 'pkg-f').status).toBe('unknown');
  });

  test('returns package/ecosystem/version metadata', () => {
    const results = Utils.checkLicenses(packages);
    const pkg = results.find(r => r.package === 'pkg-a');
    expect(pkg.ecosystem).toBe('pypi');
    expect(pkg.version).toBe('1.0.0');
  });
});

describe('_parsePolicyYaml', () => {
  test('parses boolean values', () => {
    const result = Utils._parsePolicyYaml('no-deprecated: true\nno-yanked: false');
    expect(result['no-deprecated']).toBe(true);
    expect(result['no-yanked']).toBe(false);
  });

  test('parses numeric values', () => {
    const result = Utils._parsePolicyYaml('max-vulnerabilities: 10');
    expect(result['max-vulnerabilities']).toBe(10);
  });

  test('parses inline array values', () => {
    const result = Utils._parsePolicyYaml('allowed-licenses: [MIT, Apache-2.0, BSD-3-Clause]');
    expect(result['allowed-licenses']).toEqual(['MIT', 'Apache-2.0', 'BSD-3-Clause']);
  });

  test('parses string values without quotes', () => {
    const result = Utils._parsePolicyYaml('require-vendor: acme-corp');
    expect(result['require-vendor']).toBe('acme-corp');
  });

  test('skips comments and blank lines', () => {
    const yaml = '# comment\n\nno-deprecated: true\n---\nno-yanked: false';
    const result = Utils._parsePolicyYaml(yaml);
    expect(result['no-deprecated']).toBe(true);
    expect(result['no-yanked']).toBe(false);
  });

  test('strips quotes from values', () => {
    const result = Utils._parsePolicyYaml('require-vendor: "acme-corp"');
    expect(result['require-vendor']).toBe('acme-corp');
  });

  test('returns empty object for empty input', () => {
    expect(Utils._parsePolicyYaml('')).toEqual({});
  });
});

describe('checkPolicy', () => {
  const packages = {
    'good-pkg': { deprecated: false, yanked: false },
    'bad-dep': { deprecated: true, yanked: false },
    'bad-yank': { deprecated: false, yanked: true },
  };
  const vulns = [
    { package: 'good-pkg', severity: 'LOW' },
    { package: 'good-pkg', severity: 'CRITICAL' },
  ];
  const licenses = [
    { package: 'bad-dep', license: 'GPL-3.0-only' },
    { package: 'good-pkg', license: 'MIT' },
    { package: 'bad-yank', license: 'AGPL-3.0-only' },
  ];

  test('no-deprecated detects deprecated packages', () => {
    const violations = Utils.checkPolicy(packages, 'no-deprecated: true', [], []);
    expect(violations).toHaveLength(1);
    expect(violations[0].package).toBe('bad-dep');
    expect(violations[0].rule).toBe('no-deprecated');
  });

  test('no-yanked detects yanked packages', () => {
    const violations = Utils.checkPolicy(packages, 'no-yanked: true', [], []);
    expect(violations).toHaveLength(1);
    expect(violations[0].package).toBe('bad-yank');
  });

  test('no-gpl detects GPL licenses', () => {
    const violations = Utils.checkPolicy(packages, 'no-gpl: true', [], licenses);
    expect(violations).toHaveLength(1);
    expect(violations[0].package).toBe('bad-dep');
  });

  test('no-agpl detects AGPL licenses', () => {
    const violations = Utils.checkPolicy(packages, 'no-agpl: true', [], licenses);
    expect(violations).toHaveLength(1);
    expect(violations[0].package).toBe('bad-yank');
  });

  test('max-vulnerabilities triggers when exceeded', () => {
    const violations = Utils.checkPolicy(packages, 'max-vulnerabilities: 1', vulns, []);
    expect(violations).toHaveLength(1);
    expect(violations[0].rule).toBe('max-vulnerabilities');
    expect(violations[0].package).toBe('*');
  });

  test('max-vulnerabilities does not trigger when under limit', () => {
    const violations = Utils.checkPolicy(packages, 'max-vulnerabilities: 5', vulns, []);
    expect(violations.filter(v => v.rule === 'max-vulnerabilities')).toHaveLength(0);
  });

  test('max-critical-vulns triggers when exceeded', () => {
    const violations = Utils.checkPolicy(packages, 'max-critical-vulns: 0', vulns, []);
    expect(violations).toHaveLength(1);
    expect(violations[0].rule).toBe('max-critical-vulns');
  });

  test('allowed-licenses flags unapproved licenses', () => {
    const violations = Utils.checkPolicy(packages, 'allowed-licenses: [MIT]', [], licenses);
    const flagged = violations.filter(v => v.rule === 'allowed-licenses');
    expect(flagged).toHaveLength(2);
    expect(flagged.map(v => v.package)).toEqual(expect.arrayContaining(['bad-dep', 'bad-yank']));
  });

  test('blocked-packages flags matching names', () => {
    const violations = Utils.checkPolicy(packages, 'blocked-packages: [bad-dep]', [], []);
    expect(violations).toHaveLength(1);
    expect(violations[0].package).toBe('bad-dep');
  });

  test('empty policy returns no violations', () => {
    const violations = Utils.checkPolicy(packages, '', vulns, licenses);
    expect(violations).toHaveLength(0);
  });
});

describe('generateSBOM', () => {
  const lockData = {
    metadata: { project_name: 'test-project' },
    packages: {
      flask: {
        resolved_version: '2.3.0',
        ecosystem: 'pypi',
        license: 'BSD-3-Clause',
        dependencies: { dev: [{ Werkzeug: '>=2.0' }] },
      },
      werkzeug: {
        resolved_version: '3.0.0',
        ecosystem: 'pypi',
        license: 'BSD-3-Clause',
      },
    },
  };

  test('generates valid SPDX 2.3 JSON', () => {
    const result = Utils.generateSBOM(lockData, 'spdx');
    const parsed = JSON.parse(result);
    expect(parsed.spdxVersion).toBe('SPDX-2.3');
    expect(parsed.dataLicense).toBe('CC0-1.0');
    expect(parsed.name).toBe('test-project');
    expect(parsed.creationInfo.creators).toContain('Tool: universal-dependency-resolver-frontend');
    expect(parsed.packages).toHaveLength(2);
    expect(parsed.relationships).toHaveLength(1);
    expect(parsed.relationships[0].relationshipType).toBe('DEPENDS_ON');
  });

  test('SPDX uses safe package names in SPDXID', () => {
    const result = Utils.generateSBOM(lockData, 'spdx');
    const parsed = JSON.parse(result);
    expect(parsed.packages[0].SPDXID).toBe('SPDXRef-flask');
  });

  test('generates valid CycloneDX 1.5 JSON', () => {
    const result = Utils.generateSBOM(lockData, 'cyclonedx');
    const parsed = JSON.parse(result);
    expect(parsed.bomFormat).toBe('CycloneDX');
    expect(parsed.specVersion).toBe('1.5');
    expect(parsed.version).toBe(1);
    expect(parsed.components).toHaveLength(2);
    expect(parsed.dependencies).toHaveLength(2);
  });

  test('throws for unknown format', () => {
    expect(() => Utils.generateSBOM(lockData, 'unknown')).toThrow('Unknown SBOM format');
  });

  test('uses default project name when metadata missing', () => {
    const data = { packages: { a: { resolved_version: '1.0' } } };
    const result = Utils.generateSBOM(data, 'spdx');
    expect(JSON.parse(result).name).toBe('universal-dependency-project');
  });

  test('handles empty packages object', () => {
    const data = { metadata: { project_name: 'empty' }, packages: {} };
    const spdxResult = Utils.generateSBOM(data, 'spdx');
    expect(JSON.parse(spdxResult).packages).toHaveLength(0);
    expect(JSON.parse(spdxResult).relationships).toHaveLength(0);

    const cdResult = Utils.generateSBOM(data, 'cyclonedx');
    expect(JSON.parse(cdResult).components).toHaveLength(0);
  });
});

describe('treeToGraphData', () => {
  test('converts a single node without children', () => {
    const trees = [{ name: 'root', version: '1.0', ecosystem: 'pypi' }];
    const result = Utils.treeToGraphData(trees);
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('root');
    expect(result.links).toHaveLength(0);
  });

  test('converts nested tree with children', () => {
    const trees = [{
      name: 'root',
      version: '1.0',
      ecosystem: 'pypi',
      children: [
        { name: 'child-a', version: '2.0', ecosystem: 'pypi', children: [
          { name: 'grandchild', version: '3.0', ecosystem: 'npm' },
        ]},
        { name: 'child-b', version: '1.5', ecosystem: 'crates' },
      ],
    }];
    const result = Utils.treeToGraphData(trees);
    expect(result.nodes).toHaveLength(4);
    expect(result.links).toHaveLength(3);
  });

  test('handles multiple trees', () => {
    const trees = [
      { name: 'tree1', version: '1.0', children: [] },
      { name: 'tree2', version: '2.0', children: [] },
    ];
    const result = Utils.treeToGraphData(trees);
    expect(result.nodes).toHaveLength(2);
    expect(result.links).toHaveLength(0);
  });

  test('deduplicates edges between same nodes', () => {
    const trees = [{
      name: 'root',
      children: [
        { name: 'child' },
        { name: 'child' },
      ],
    }];
    const result = Utils.treeToGraphData(trees);
    expect(result.links).toHaveLength(1);
  });

  test('handles null/undefined/empty input', () => {
    expect(Utils.treeToGraphData(null).nodes).toHaveLength(0);
    expect(Utils.treeToGraphData(undefined).nodes).toHaveLength(0);
    expect(Utils.treeToGraphData([]).nodes).toHaveLength(0);
  });
});

describe('downloadFile', () => {
  beforeEach(() => {
    URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    URL.revokeObjectURL = jest.fn();
  });

  test('creates blob and triggers download', () => {
    Utils.downloadFile('{"test": true}', 'test.json');
    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  test('stringifies object content automatically', () => {
    Utils.downloadFile({ key: 'value' }, 'data.json');
    expect(URL.createObjectURL).toHaveBeenCalled();
  });
});

describe('readFileAsText', () => {
  test('resolves with file content', async () => {
    const file = new File(['hello world'], 'test.txt', { type: 'text/plain' });
    const result = await Utils.readFileAsText(file);
    expect(result).toBe('hello world');
  });
});

describe('checkVulnerabilitiesOSV', () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('queries OSV API and returns parsed vulns with severity HIGH', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        vulns: [{
          id: 'GHSA-xxxx-xxxx-xxxx',
          aliases: ['CVE-2024-0001'],
          summary: 'Test vuln summary',
          severity: [{ type: 'CVSS_V3', score: 7.5 }],
          affected: [{ ranges: [{ events: [{ fixed: '2.3.1' }] }] }],
        }],
      }),
    });

    const results = await Utils.checkVulnerabilitiesOSV({
      flask: { ecosystem: 'pypi', resolved_version: '2.3.0' },
    });

    expect(results).toHaveLength(1);
    expect(results[0].id).toBe('GHSA-xxxx-xxxx-xxxx');
    expect(results[0].package).toBe('flask');
    expect(results[0].severity).toBe('HIGH');
    expect(results[0].fixedVersion).toBe('2.3.1');
  });

  test('maps severity correctly across thresholds', async () => {
    const mockFetch = jest.fn();
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ vulns: [{ id: 'GHSA-h', aliases: [], severity: [{ type: 'CVSS_V3', score: 8.0 }] }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ vulns: [{ id: 'GHSA-m', aliases: [], severity: [{ type: 'CVSS_V3', score: 5.5 }] }] }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ vulns: [{ id: 'GHSA-l', aliases: [], severity: [{ type: 'CVSS_V3', score: 2.0 }] }] }),
      });
    global.fetch = mockFetch;

    const resultsHigh = await Utils.checkVulnerabilitiesOSV({ a: { ecosystem: 'npm', resolved_version: '1.0.0' } });
    expect(resultsHigh[0].severity).toBe('HIGH');

    const resultsMod = await Utils.checkVulnerabilitiesOSV({ b: { ecosystem: 'npm', resolved_version: '1.0.0' } });
    expect(resultsMod[0].severity).toBe('MODERATE');

    const resultsLow = await Utils.checkVulnerabilitiesOSV({ c: { ecosystem: 'npm', resolved_version: '1.0.0' } });
    expect(resultsLow[0].severity).toBe('LOW');
  });

  test('makes correct POST request to OSV API', async () => {
    global.fetch.mockResolvedValue({ ok: false });
    await Utils.checkVulnerabilitiesOSV({
      lodash: { ecosystem: 'npm', resolved_version: '1.0.0' },
    });
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.osv.dev/v1/query',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.package.name).toBe('lodash');
    expect(body.package.ecosystem).toBe('npm');
  });

  test('defaults ecosystem to PyPI when not provided', async () => {
    global.fetch.mockResolvedValue({ ok: false });
    await Utils.checkVulnerabilitiesOSV({
      pkg: { resolved_version: '1.0.0' },
    });
    const body = JSON.parse(global.fetch.mock.calls[0][1].body);
    expect(body.package.ecosystem).toBe('PyPI');
  });

  test('handles non-OK response gracefully', async () => {
    global.fetch.mockResolvedValue({ ok: false });
    const results = await Utils.checkVulnerabilitiesOSV({
      flask: { ecosystem: 'pypi', resolved_version: '1.0.0' },
    });
    expect(results).toHaveLength(0);
  });

  test('handles fetch network errors gracefully', async () => {
    global.fetch.mockRejectedValue(new Error('Network error'));
    const results = await Utils.checkVulnerabilitiesOSV({
      flask: { ecosystem: 'pypi', resolved_version: '1.0.0' },
    });
    expect(results).toHaveLength(0);
  });

  test('skips packages without version', async () => {
    const results = await Utils.checkVulnerabilitiesOSV({
      flask: { ecosystem: 'pypi' },
    });
    expect(results).toHaveLength(0);
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
