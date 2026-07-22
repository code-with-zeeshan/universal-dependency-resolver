/**
 * Tests for BackendAPI class (js/api.js).
 *
 * Each test verifies that the correct HTTP method, URL, and body are sent,
 * and that responses are parsed correctly.
 */

const fs = require('fs');
const path = require('path');

// Load and patch api.js so BackendAPI is available
const apiSource = fs.readFileSync(path.join(__dirname, '..', 'js', 'api.js'), 'utf8');
const patched = apiSource
  .replace('class BackendAPI', 'globalThis.BackendAPI = class BackendAPI')
  .replace('const api = new BackendAPI();', '');
eval(patched);

if (typeof AbortSignal !== 'undefined' && !AbortSignal.timeout) {
  AbortSignal.timeout = function timeout(ms) {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), ms);
    return ctrl.signal;
  };
}

const BASE = 'http://localhost:8199';

function mockFetch(status, body) {
  const res = {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 404 ? 'Not Found' : status === 500 ? 'Internal Server Error' : 'OK',
    json: () => Promise.resolve(body),
  };
  global.fetch.mockResolvedValue(res);
}

let api;

beforeEach(() => {
  global.fetch = jest.fn();
  global.fetch.mockClear();
  api = new BackendAPI();
});

describe('BackendAPI — constructor', () => {
  test('defaults to localhost:8199', () => {
    expect(api.baseURL).toBe('http://localhost:8199');
    expect(api.apiPrefix).toBe('/api/v1');
  });

  test('strips trailing slash from base URL', () => {
    const a = new BackendAPI('http://example.com/');
    expect(a.baseURL).toBe('http://example.com');
  });

  test('accepts custom base URL', () => {
    const a = new BackendAPI('http://custom:1234');
    expect(a.baseURL).toBe('http://custom:1234');
  });
});

describe('BackendAPI — _fetch', () => {
  beforeEach(() => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'ok' }),
    });
  });

  test('sends GET request by default', async () => {
    await api._fetch('/test');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/test`,
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  test('sends POST when method specified', async () => {
    await api._fetch('/test', { method: 'POST', body: '{}' });
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/test`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('sets Content-Type header', async () => {
    await api._fetch('/test');
    const call = global.fetch.mock.calls[0][1];
    expect(call.headers['Content-Type']).toBe('application/json');
  });

  test('adds Authorization header when token provided', async () => {
    await api._fetch('/test', { token: 'abc123' });
    const call = global.fetch.mock.calls[0][1];
    expect(call.headers['Authorization']).toBe('Bearer abc123');
  });

  test('throws on non-ok response', async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 404,
      statusText: 'Not Found',
      json: () => Promise.resolve({ detail: 'Package not found' }),
    });
    await expect(api._fetch('/test')).rejects.toThrow('404: Package not found');
  });

  test('throws on timeout', async () => {
    const err = new Error('timeout');
    err.name = 'TimeoutError';
    global.fetch.mockRejectedValue(err);
    await expect(api._fetch('/test')).rejects.toThrow('Request timed out');
  });
});

describe('BackendAPI — health', () => {
  test('checkHealth hits /healthz', async () => {
    mockFetch(200, { status: 'healthy' });
    const result = await api.checkHealth();
    expect(global.fetch).toHaveBeenCalledWith(`${BASE}/healthz`, expect.any(Object));
    expect(result).toEqual({ status: 'healthy' });
  });

  test('getFullHealth hits /api/v1/health', async () => {
    mockFetch(200, { healthy: true });
    await api.getFullHealth();
    expect(global.fetch).toHaveBeenCalledWith(`${BASE}/api/v1/health`, expect.any(Object));
  });
});

describe('BackendAPI — system', () => {
  test('getSystemInfo hits /system/info', async () => {
    mockFetch(200, { platform: {} });
    await api.getSystemInfo();
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/system/info`,
      expect.any(Object),
    );
  });

  test('getSystemInfo with detailed=true appends query', async () => {
    mockFetch(200, { platform: {} });
    await api.getSystemInfo(true);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/system/info?detailed=true`,
      expect.any(Object),
    );
  });
});

describe('BackendAPI — packages', () => {
  test('searchPackages builds query string', async () => {
    mockFetch(200, { results: [] });
    await api.searchPackages('requests', ['pypi', 'npm'], 10);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/search?q=requests&limit=10&ecosystems=pypi%2Cnpm`,
      expect.any(Object),
    );
  });

  test('getPackageDetails constructs path', async () => {
    mockFetch(200, {});
    await api.getPackageDetails('requests', 'pypi');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/pypi/requests/details`,
      expect.any(Object),
    );
  });

  test('getPackageDetails defaults to pypi', async () => {
    mockFetch(200, {});
    await api.getPackageDetails('foo');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/pypi/foo/details`,
      expect.any(Object),
    );
  });

  test('getPackageVersions constructs path with options', async () => {
    mockFetch(200, { versions: [] });
    await api.getPackageVersions('foo', 'npm', { includeYanked: true, includePrerelease: true });
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/npm/foo/versions?include_yanked=true&include_prerelease=true`,
      expect.any(Object),
    );
  });

  test('getPackageDependencies constructs path', async () => {
    mockFetch(200, { dependencies: [] });
    await api.getPackageDependencies('foo', 'pypi', '1.0.0', true, 5);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/dependencies'),
      expect.any(Object),
    );
    const url = global.fetch.mock.calls[0][0];
    expect(url).toContain('version=1.0.0');
    expect(url).toContain('recursive=true');
    expect(url).toContain('max_depth=5');
  });

  test('getPackageCompatibility constructs path', async () => {
    mockFetch(200, { compatible: true });
    await api.getPackageCompatibility('foo', 'pypi', '2.0.0');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/pypi/foo/compatibility?version=2.0.0`,
      expect.any(Object),
    );
  });

  test('getEcosystems hits /packages/ecosystems', async () => {
    mockFetch(200, { ecosystems: [] });
    await api.getEcosystems();
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/ecosystems`,
      expect.any(Object),
    );
  });
});

describe('BackendAPI — POST methods', () => {
  test('resolvePackages sends POST with JSON body', async () => {
    mockFetch(200, { resolved: {} });
    const pkgs = [{ name: 'foo', ecosystem: 'pypi' }];
    await api.resolvePackages(pkgs);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/resolve`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ packages: pkgs, auto_detect_system: true }),
      }),
    );
  });

  test('generateLock sends POST', async () => {
    mockFetch(200, { lock_data: {} });
    await api.generateLock({ ecosystem: 'pypi' });
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/generate-lock`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('verifyLock sends POST', async () => {
    mockFetch(200, { ok: true });
    await api.verifyLock({ packages: {} });
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/verify`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('whyPackage sends POST', async () => {
    mockFetch(200, { paths: [] });
    await api.whyPackage({ packages: {} }, 'foo');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/why`,
      expect.objectContaining({
        method: 'POST',
        body: expect.stringContaining('"package":"foo"'),
      }),
    );
  });

  test('getOutdated sends POST', async () => {
    mockFetch(200, { outdated: [] });
    await api.getOutdated({ packages: {} }, 'pypi');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/outdated`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('diffLocks sends POST with two lock data objects', async () => {
    mockFetch(200, { diff: [] });
    await api.diffLocks({ a: 1 }, { b: 2 });
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/diff`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ lock_a: { a: 1 }, lock_b: { b: 2 } }),
      }),
    );
  });

  test('exportPackages sends POST', async () => {
    mockFetch(200, { export: '' });
    await api.exportPackages({ foo: {} }, 'requirements', {}, {});
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/packages/export`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('checkSystemCompatibility sends POST', async () => {
    mockFetch(200, { compatible: true });
    await api.checkSystemCompatibility({ os: 'linux' }, ['foo']);
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/system/check-compatibility`,
      expect.objectContaining({ method: 'POST' }),
    );
  });

  test('scanGithub sends POST', async () => {
    mockFetch(200, { findings: [] });
    await api.scanGithub('https://github.com/user/repo');
    expect(global.fetch).toHaveBeenCalledWith(
      `${BASE}/api/v1/scan/github`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ repo_url: 'https://github.com/user/repo' }),
      }),
    );
  });
});
