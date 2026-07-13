class BackendAPI {
  constructor(baseURL = 'http://localhost:8199') {
    this.baseURL = baseURL.replace(/\/+$/, '');
    this.apiPrefix = '/api/v1';
  }

  async _fetch(path, options = {}) {
    const url = `${this.baseURL}${path}`;
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (options.token) {
      headers['Authorization'] = `Bearer ${options.token}`;
    }
    try {
      const res = await fetch(url, { ...options, headers, signal: AbortSignal.timeout(30000) });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        const msg = body?.detail || body?.error?.message || res.statusText;
        throw new Error(`${res.status}: ${msg}`);
      }
      return res.json();
    } catch (err) {
      if (err.name === 'TimeoutError' || err.name === 'AbortError') {
        throw new Error('Request timed out');
      }
      throw err;
    }
  }

  checkHealth() {
    return this._fetch('/healthz');
  }

  getFullHealth() {
    return this._fetch(`${this.apiPrefix}/health`);
  }

  getSystemInfo(detailed = false) {
    const qs = detailed ? '?detailed=true' : '';
    return this._fetch(`${this.apiPrefix}/system/info${qs}`);
  }

  searchPackages(query, ecosystems = null, limit = 20) {
    let path = `${this.apiPrefix}/packages/search?q=${encodeURIComponent(query)}&limit=${limit}`;
    if (ecosystems) path += `&ecosystems=${encodeURIComponent(ecosystems.join(','))}`;
    return this._fetch(path);
  }

  getPackageDetails(name, ecosystem = 'pypi') {
    return this._fetch(`${this.apiPrefix}/packages/${ecosystem}/${encodeURIComponent(name)}/details`);
  }

  getPackageVersions(name, ecosystem = 'pypi', opts = {}) {
    let path = `${this.apiPrefix}/packages/${ecosystem}/${encodeURIComponent(name)}/versions`;
    const qs = [];
    if (opts.includeYanked) qs.push('include_yanked=true');
    if (opts.includePrerelease) qs.push('include_prerelease=true');
    if (qs.length) path += '?' + qs.join('&');
    return this._fetch(path);
  }

  getPackageDependencies(name, ecosystem = 'pypi', version = null, recursive = false, maxDepth = 3) {
    let path = `${this.apiPrefix}/packages/${ecosystem}/${encodeURIComponent(name)}/dependencies`;
    const qs = [];
    if (version) qs.push(`version=${encodeURIComponent(version)}`);
    if (recursive) qs.push('recursive=true');
    if (recursive && maxDepth !== 3) qs.push(`max_depth=${maxDepth}`);
    if (qs.length) path += '?' + qs.join('&');
    return this._fetch(path);
  }

  getPackageCompatibility(name, ecosystem = 'pypi', version = null) {
    let path = `${this.apiPrefix}/packages/${ecosystem}/${encodeURIComponent(name)}/compatibility`;
    if (version) path += `?version=${encodeURIComponent(version)}`;
    return this._fetch(path);
  }

  resolvePackages(packages, autoDetectSystem = true) {
    return this._fetch(`${this.apiPrefix}/packages/resolve`, {
      method: 'POST',
      body: JSON.stringify({ packages, auto_detect_system: autoDetectSystem }),
    });
  }

  getGraph(packages, ecosystem = 'pypi') {
    return this._fetch(`${this.apiPrefix}/graph`, {
      method: 'POST',
      body: JSON.stringify({ packages, ecosystem }),
    });
  }

  verifyLock(lockData) {
    return this._fetch(`${this.apiPrefix}/verify`, {
      method: 'POST',
      body: JSON.stringify({ lock_data: lockData }),
    });
  }

  updateLock(lockData, packageName, ecosystem = null) {
    return this._fetch(`${this.apiPrefix}/update`, {
      method: 'POST',
      body: JSON.stringify({ lock_data: lockData, package: packageName, ecosystem }),
    });
  }

  generateLock(params) {
    return this._fetch(`${this.apiPrefix}/generate-lock`, {
      method: 'POST',
      body: JSON.stringify(params),
    });
  }

  whyPackage(lockData, packageName) {
    return this._fetch(`${this.apiPrefix}/why`, {
      method: 'POST',
      body: JSON.stringify({ lock_data: lockData, package: packageName }),
    });
  }

  getOutdated(lockData, ecosystem = null) {
    return this._fetch(`${this.apiPrefix}/outdated`, {
      method: 'POST',
      body: JSON.stringify({ lock_data: lockData, ecosystem }),
    });
  }

  diffLocks(lockData1, lockData2) {
    return this._fetch(`${this.apiPrefix}/diff`, {
      method: 'POST',
      body: JSON.stringify({ lock_data_a: lockData1, lock_data_b: lockData2 }),
    });
  }

  getInstallCommands(lockData) {
    return this._fetch(`${this.apiPrefix}/install-commands`, {
      method: 'POST',
      body: JSON.stringify({ lock_data: lockData }),
    });
  }

  getEcosystems() {
    return this._fetch(`${this.apiPrefix}/packages/ecosystems`);
  }

  exportPackages(resolvedPackages, format, systemInfo = {}, options = {}) {
    return this._fetch(`${this.apiPrefix}/packages/export`, {
      method: 'POST',
      body: JSON.stringify({
        resolved_packages: resolvedPackages,
        format,
        system_info: systemInfo,
        options,
      }),
    });
  }

  getExportFormats() {
    return this._fetch(`${this.apiPrefix}/packages/export-formats`);
  }

  checkSystemCompatibility(requirements, packages = null) {
    return this._fetch(`${this.apiPrefix}/system/check-compatibility`, {
      method: 'POST',
      body: JSON.stringify({ requirements, packages }),
    });
  }

  scanGithub(repoUrl) {
    return this._fetch(`${this.apiPrefix}/scan/github`, {
      method: 'POST',
      body: JSON.stringify({ repo_url: repoUrl }),
    });
  }
}

const api = new BackendAPI();
