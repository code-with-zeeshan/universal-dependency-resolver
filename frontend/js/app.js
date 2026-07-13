const App = {
  state: {
    currentPage: 'dashboard',
    lockData: null,
    lockFileName: null,
    cachedSystemInfo: null,
    cachedHealth: null,
    searchResults: null,
    graphData: null,
    cveResults: null,
    licenseResults: null,
    policyResults: null,
    sbomContent: null,
    selectedTab: {},
  },

  init() {
    this._setupEventListeners();
    this._setupFileDrops();
    this._checkHealth();
    this._handleRoute();
    window.addEventListener('hashchange', () => this._handleRoute());
  },

  _handleRoute() {
    const hash = window.location.hash.slice(1) || 'dashboard';
    if (!document.getElementById(`page-${hash}`)) hash = 'dashboard';
    this._showPage(hash);
    if (hash === 'dashboard') this._renderDashboard();
    else if (hash === 'search') this._renderSearch();
    else if (hash === 'graph') this._renderGraph();
    else if (hash === 'lock') this._renderLockViewer();
    else if (hash === 'cve') this._renderCVE();
    else if (hash === 'sbom') this._renderSBOM();
    else if (hash === 'policy') this._renderPolicy();
    else if (hash === 'system') this._renderSystemInfo();
  },

  _showPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.sidebar a').forEach(a => a.classList.remove('active'));
    const page = document.getElementById(`page-${name}`);
    if (page) page.classList.add('active');
    const link = document.querySelector(`.sidebar a[href="#${name}"]`);
    if (link) link.classList.add('active');
    this.state.currentPage = name;
    if (window.innerWidth <= 768) this._closeSidebar();
  },

  _closeSidebar() {
    document.querySelector('.sidebar').classList.remove('open');
    document.querySelector('.sidebar-backdrop').classList.remove('open');
  },

  async _checkHealth() {
    const dot = document.getElementById('status-dot');
    const text = document.getElementById('status-text');
    dot.className = 'status-dot checking';
    text.textContent = 'Checking...';
    try {
      const data = await api.checkHealth();
      if (data?.status === 'ok') {
        dot.className = 'status-dot online';
        text.textContent = 'Connected';
        this.state.cachedHealth = data;
      } else throw new Error('unhealthy');
    } catch {
      dot.className = 'status-dot offline';
      text.textContent = 'Disconnected';
    }
  },

  _setupEventListeners() {
    document.querySelector('.menu-toggle')?.addEventListener('click', () => {
      document.querySelector('.sidebar').classList.toggle('open');
      document.querySelector('.sidebar-backdrop').classList.toggle('open');
    });
    document.querySelector('.sidebar-backdrop')?.addEventListener('click', () => this._closeSidebar());
    document.getElementById('search-form')?.addEventListener('submit', e => {
      e.preventDefault();
      this._doSearch();
    });
    document.getElementById('graph-form')?.addEventListener('submit', e => {
      e.preventDefault();
      this._doGraph();
    });
    document.getElementById('sbom-form')?.addEventListener('submit', e => {
      e.preventDefault();
      this._generateSBOM();
    });
    document.getElementById('cve-run')?.addEventListener('click', () => this._runCVE());
    document.getElementById('policy-run')?.addEventListener('click', () => this._runPolicy());
    document.getElementById('lock-verify')?.addEventListener('click', () => this._verifyLock());
    document.getElementById('lock-outdated')?.addEventListener('click', () => this._checkOutdated());
    document.getElementById('system-refresh')?.addEventListener('click', () => this._renderSystemInfo(true));
  },

  _setupFileDrops() {
    ['lock-drop', 'policy-drop', 'lock-drop-cve', 'lock-drop-sbom'].forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('drag-over'); });
      el.addEventListener('dragleave', () => el.classList.remove('drag-over'));
      el.addEventListener('drop', async e => {
        e.preventDefault();
        el.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (!file) return;
        await this._handleFileDrop(id, file);
      });
      const input = el.querySelector('input[type="file"]');
      if (input) {
        input.addEventListener('change', async e => {
          if (e.target.files[0]) await this._handleFileDrop(id, e.target.files[0]);
        });
      }
    });
  },

  async _handleFileDrop(dropId, file) {
    try {
      const text = await Utils.readFileAsText(file);
      if (dropId === 'lock-drop' || dropId === 'lock-drop-cve' || dropId === 'lock-drop-sbom') {
        this.state.lockData = Utils.parseLockFile(text);
        this.state.lockFileName = file.name;
        Utils.makeToast(`Loaded lock file: ${file.name}`, 'success');
        this._updateLockInfo();
      } else if (dropId === 'policy-drop') {
        this.state.policyYaml = text;
        document.getElementById('policy-yaml').value = text;
        Utils.makeToast('Loaded policy file', 'success');
      }
    } catch (err) {
      Utils.makeToast(err.message, 'error');
    }
  },

  _updateLockInfo() {
    const pkgs = Utils.getPackagesFromLock(this.state.lockData);
    const count = Object.keys(pkgs).length;
    document.querySelectorAll('.lock-count').forEach(el => el.textContent = count);
    document.querySelectorAll('.lock-name').forEach(el => el.textContent = this.state.lockFileName || 'udr.lock');
  },

  /* ====== Dashboard ====== */
  async _renderDashboard() {
    const el = document.getElementById('dashboard-content');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner spinner-lg"></div><span>Loading dashboard...</span></div>';

    try {
      const [health, sysInfo] = await Promise.all([
        api.getFullHealth().catch(() => ({ status: 'unhealthy', checks: {} })),
        api.getSystemInfo().catch(() => ({ status: 'error', system: {} })),
      ]);

      const sys = sysInfo?.system || {};
      const checks = health?.checks || {};
      const pkgCount = this.state.lockData ? Utils.getPackageCount(this.state.lockData) : 0;

      let vulnBadge = '';
      if (this.state.cveResults && this.state.cveResults.length > 0) {
        const crit = this.state.cveResults.filter(v => v.severity === 'CRITICAL' || v.severity === 'HIGH').length;
        vulnBadge = ` <span class="badge badge-red">${crit} critical</span>`;
      }

      el.innerHTML = `
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">API Status</div>
            <div class="stat-value" style="color:${health.status === 'healthy' ? 'var(--green)' : 'var(--red)'}">
              ${health.status === 'healthy' ? 'Healthy' : 'Unhealthy'}
            </div>
            <div class="stat-sub">${health.status === 'healthy' ? 'All systems operational' : 'Some services degraded'}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Packages in Lock</div>
            <div class="stat-value">${pkgCount || '—'}</div>
            <div class="stat-sub">${this.state.lockFileName || 'No lock file loaded'}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">OS</div>
            <div class="stat-value" style="font-size:1.2rem">${sys.os || 'Unknown'}</div>
            <div class="stat-sub">${sys.python ? 'Python ' + sys.python : ''}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">GPU / CUDA</div>
            <div class="stat-value" style="font-size:1rem">${sys.gpu || 'None detected'}</div>
            <div class="stat-sub">${sys.cuda ? 'CUDA ' + sys.cuda : ''}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Database</div>
            <div class="stat-value" style="font-size:1rem;color:${checks.database?.status === 'healthy' ? 'var(--green)' : 'var(--red)'}">
              ${checks.database?.status || 'Unknown'}
            </div>
            <div class="stat-sub">PostgreSQL</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">External APIs</div>
            <div class="stat-value" style="font-size:1rem;color:${checks.external_apis?.status === 'healthy' ? 'var(--green)' : 'var(--yellow)'}">
              ${checks.external_apis?.status || 'Unknown'}
            </div>
            <div class="stat-sub">PyPI ${checks.external_apis?.pypi || '?'}</div>
          </div>
        </div>

        ${this.state.lockData ? `
        <div class="card">
          <div class="card-title">Loaded Lock File: ${Utils.escapeHtml(this.state.lockFileName)}</div>
          <div class="lock-summary">
            <div class="lock-stat"><div class="num">${pkgCount}</div><div class="lbl">Packages</div></div>
            <div class="lock-stat"><div class="num">${this.state.cveResults ? this.state.cveResults.length : '?'}</div><div class="lbl">Vulnerabilities ${vulnBadge}</div></div>
            <div class="lock-stat"><div class="num">${this.state.licenseResults ? this.state.licenseResults.filter(l => l.status === 'restricted').length : '?'}</div><div class="lbl">License Issues</div></div>
          </div>
        </div>
        ` : `
        <div class="card">
          <div class="card-title">Get Started</div>
          <p class="text-secondary">Load a <code>udr.lock</code> file to view its contents, check for vulnerabilities, generate SBOMs, and more.</p>
          <div class="btn-group mt-2">
            <a href="#lock" class="btn btn-primary">Load Lock File</a>
            <a href="#system" class="btn">View System Info</a>
            <a href="#search" class="btn">Search Packages</a>
          </div>
        </div>
        `}

        <div class="card">
          <div class="card-title">Quick Actions</div>
          <div class="btn-group">
            <a href="#lock" class="btn">${this.state.lockData ? 'View Lock' : 'Load Lock'}</a>
            <a href="#cve" class="btn">${this.state.lockData ? 'Check CVEs' : 'CVE Check'}</a>
            <a href="#sbom" class="btn">${this.state.lockData ? 'Generate SBOM' : 'Generate SBOM'}</a>
            <a href="#policy" class="btn">Policy Check</a>
            <a href="#graph" class="btn">Dependency Graph</a>
            <a href="#system" class="btn">System Info</a>
          </div>
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><div class="icon">&#9888;</div><h3>Failed to load dashboard</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  /* ====== Search ====== */
  _renderSearch() {
    const el = document.getElementById('search-content');
    if (!this.state.searchResults) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="icon">&#128269;</div>
          <h3>Search Packages</h3>
          <p>Search across PyPI, npm, crates.io, and more ecosystems.</p>
        </div>
      `;
    }
  },

  async _doSearch() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;
    const eco = document.getElementById('search-eco').value;
    const el = document.getElementById('search-results');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Searching...</span></div>';

    try {
      const data = await api.searchPackages(query, eco ? [eco] : null);
      this.state.searchResults = data;
      if (data.status !== 'success') throw new Error(data.detail || 'Search failed');

      let html = '';
      const results = data.results || {};
      let total = 0;
      Object.entries(results).forEach(([ecoName, pkgs]) => {
        if (!Array.isArray(pkgs) || pkgs.length === 0) return;
        total += pkgs.length;
        html += `<h3 class="mb-2">${Utils.ecoBadge(ecoName)} ${pkgs.length} result${pkgs.length === 1 ? '' : 's'}</h3>`;
        html += '<div class="table-container"><table><thead><tr><th>Name</th><th>Latest</th><th>Description</th></tr></thead><tbody>';
        pkgs.forEach(p => {
          const name = typeof p === 'string' ? p : p.name || p.package || '?';
          const ver = typeof p === 'string' ? '' : p.latest_version || p.version || '';
          const desc = typeof p === 'string' ? '' : (p.description || '').substring(0, 100);
          html += `<tr><td><a href="#" onclick="App._showPackageDetail('${Utils.escapeHtml(name)}', '${Utils.escapeHtml(ecoName)}'); return false;"><strong>${Utils.escapeHtml(name)}</strong></a></td>
            <td class="version-cell">${ver ? Utils.escapeHtml(ver) : '—'}</td>
            <td class="text-secondary text-sm">${Utils.escapeHtml(desc)}</td></tr>`;
        });
        html += '</tbody></table></div>';
      });

      if (total === 0) {
        html = `<div class="empty-state"><h3>No results found</h3><p>Try a different search query or ecosystem.</p></div>`;
      } else {
        html = `<p class="text-secondary mb-2">${total} package${total === 1 ? '' : 's'} found</p>` + html;
      }
      el.innerHTML = html;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><h3>Search failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  async _showPackageDetail(name, ecosystem) {
    const el = document.getElementById('search-results');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Loading details...</span></div>';
    try {
      const [details, versions, deps] = await Promise.all([
        api.getPackageDetails(name, ecosystem).catch(() => null),
        api.getPackageVersions(name, ecosystem, { includePrerelease: false }).catch(() => null),
        api.getPackageDependencies(name, ecosystem).catch(() => null),
      ]);

      const info = details?.data?.info || {};
      const desc = info.description || 'No description available';
      const verList = versions?.versions || [];
      const depList = deps?.dependencies || [];

      let html = `<a href="#" onclick="App._doSearch(); return false;" class="btn btn-sm mb-4">&larr; Back to search</a>`;
      html += `<div class="card"><div class="card-title">${Utils.escapeHtml(name)} ${Utils.ecoBadge(ecosystem)}</div>`;
      html += `<p class="text-secondary mb-4">${Utils.escapeHtml(desc)}</p>`;
      html += `<div class="info-grid">
        <span class="label">Latest Version</span><span class="value">${Utils.escapeHtml(info.latest_version || '—')}</span>
        <span class="label">Homepage</span><span class="value">${info.homepage ? `<a href="${Utils.escapeHtml(info.homepage)}" target="_blank">${Utils.escapeHtml(info.homepage)}</a>` : '—'}</span>
        <span class="label">Repository</span><span class="value">${info.repository ? `<a href="${Utils.escapeHtml(info.repository)}" target="_blank">${Utils.escapeHtml(info.repository)}</a>` : '—'}</span>
      </div></div>`;

      if (verList.length > 0) {
        html += `<div class="card"><div class="card-title">Versions (${verList.length})</div>`;
        html += '<div class="table-container"><table><thead><tr><th>Version</th><th>Published</th><th>Status</th></tr></thead><tbody>';
        verList.slice(0, 50).forEach(v => {
          const verStr = typeof v === 'string' ? v : v.version || '?';
          const pub = typeof v === 'string' ? '' : v.published || v.upload_time || '';
          const yanked = typeof v === 'string' ? false : v.yanked;
          html += `<tr><td class="version-cell">${Utils.escapeHtml(verStr)}</td>
            <td class="text-secondary text-sm">${Utils.formatDate(pub)}</td>
            <td>${yanked ? '<span class="badge badge-red">Yanked</span>' : '<span class="badge badge-green">Active</span>'}</td></tr>`;
        });
        html += '</tbody></table></div></div>';
      }

      if (depList.length > 0) {
        html += `<div class="card"><div class="card-title">Dependencies (${depList.length})</div>`;
        html += '<div class="table-container"><table><thead><tr><th>Package</th><th>Constraint</th></tr></thead><tbody>';
        depList.forEach(d => {
          const dName = d.name || d.package || Object.keys(d)[0] || '?';
          const dVer = d.constraint || d.version || d.requirement || d[dName] || '';
          html += `<tr><td>${Utils.escapeHtml(dName)}</td><td class="version-cell text-secondary">${Utils.escapeHtml(dVer)}</td></tr>`;
        });
        html += '</tbody></table></div></div>';
      }

      el.innerHTML = html;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><h3>Failed to load details</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  /* ====== Graph ====== */
  _renderGraph() {
    // No-op, form is in HTML
  },

  async _doGraph() {
    const input = document.getElementById('graph-input').value.trim();
    if (!input) return;
    const eco = document.getElementById('graph-eco').value;
    const packages = input.split(',').map(s => s.trim()).filter(Boolean);
    const el = document.getElementById('graph-output');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Resolving dependency graph...</span></div>';

    try {
      const data = await api.getGraph(packages, eco);
      this.state.graphData = data;
      if (data.status !== 'success') throw new Error(data.detail || 'Graph resolution failed');

      const trees = data.trees || [];
      const container = document.getElementById('graph-canvas-container');
      container.style.display = 'block';

      const graphData = Utils.treeToGraphData(trees);
      const svg = document.getElementById('graph-svg');
      const tooltip = document.getElementById('graph-tooltip');
      const countEl = document.getElementById('graph-node-count');
      Utils.drawForceGraph(svg, tooltip, countEl, graphData);

      el.innerHTML = `
        <div class="card mt-4">
          <div class="card-title">Tree View <span class="text-sm text-secondary">${trees.length} package tree${trees.length === 1 ? '' : 's'}</span></div>
          ${trees.map(t => this._renderTree(t)).join('')}
        </div>`;
    } catch (err) {
      document.getElementById('graph-canvas-container').style.display = 'none';
      el.innerHTML = `<div class="empty-state"><h3>Graph resolution failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  _renderTree(node, depth = 0) {
    if (!node) return '';
    const pad = depth * 20;
    const hasChildren = node.children && node.children.length > 0;
    const arrow = hasChildren ? '<span class="arrow">&#9660;</span> ' : '';
    const toggleClass = depth > 2 ? ' collapsed' : '';
    const html = `<li style="padding-left:${pad + 20}px">
      <span class="tree-toggle${toggleClass}" onclick="this.classList.toggle('collapsed')">${arrow}</span>
      <strong>${Utils.escapeHtml(node.name)}</strong>
      <span class="version-cell text-secondary ml-2">${node.version || ''}</span>
      ${node.ecosystem ? Utils.ecoBadge(node.ecosystem) : ''}
      ${hasChildren ? `<ul>${(node.children || []).map(c => this._renderTree(c, depth + 1)).join('')}</ul>` : ''}
    </li>`;
    if (depth === 0) return `<ul class="tree">${html}</ul>`;
    return html;
  },

  /* ====== Lock Viewer ====== */
  _renderLockViewer() {
    const drop = document.getElementById('lock-content');
    if (!this.state.lockData) {
      return;
    }
    this._displayLockData();
  },

  _displayLockData() {
    const el = document.getElementById('lock-content');
    if (!this.state.lockData) {
      el.innerHTML = `<div class="empty-state"><div class="icon">&#128196;</div><h3>No lock file loaded</h3><p>Drop a <code>udr.lock</code> file or click to browse.</p></div>`;
      return;
    }

    const pkgs = Utils.getPackagesFromLock(this.state.lockData);
    const entries = Object.entries(pkgs);
    const direct = entries.filter(([, v]) => v.direct !== false);
    const transitive = entries.filter(([, v]) => v.direct === false);

    let html = `<div class="lock-summary mb-4">
      <div class="lock-stat"><div class="num">${entries.length}</div><div class="lbl">Total Packages</div></div>
      <div class="lock-stat"><div class="num">${direct.length}</div><div class="lbl">Direct</div></div>
      <div class="lock-stat"><div class="num">${transitive.length}</div><div class="lbl">Transitive</div></div>
    </div>`;

    html += `<div class="btn-group mb-4">
      <button class="btn btn-sm" onclick="App._verifyLock()">Verify</button>
      <button class="btn btn-sm" onclick="App._checkOutdated()">Check Outdated</button>
      <button class="btn btn-sm" onclick="App._exportLock()">Export</button>
      <button class="btn btn-sm" onclick="App._clearLock()">Clear</button>
    </div>`;

    html += '<div class="table-container"><table><thead><tr><th>Package</th><th>Version</th><th>Ecosystem</th><th>Type</th><th>License</th><th>Integrity</th></tr></thead><tbody>';
    entries.forEach(([name, info]) => {
      const ver = info.resolved_version || info.version || '?';
      const eco = info.ecosystem || '?';
      const type = info.direct !== false ? '<span class="badge badge-blue">Direct</span>' : '<span class="badge badge-cyan">Transitive</span>';
      const lic = info.license || info.license_name || '';
      const integ = info.integrity || info.hash || '';
      html += `<tr>
        <td><strong>${Utils.escapeHtml(name)}</strong></td>
        <td class="version-cell">${Utils.escapeHtml(ver)}</td>
        <td>${Utils.ecoBadge(eco)}</td>
        <td>${type}</td>
        <td>${lic ? `<span class="badge badge-purple">${Utils.escapeHtml(lic)}</span>` : '—'}</td>
        <td class="text-muted text-sm" style="max-width:120px;overflow:hidden;text-overflow:ellipsis">${integ ? Utils.truncate(integ, 20) : '—'}</td>
      </tr>`;
    });
    html += '</tbody></table></div>';

    el.innerHTML = html;
  },

  async _verifyLock() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    const btn = document.getElementById('lock-verify');
    btn.disabled = true;
    btn.textContent = 'Verifying...';
    try {
      const data = await api.verifyLock(this.state.lockData);
      let msg = `Verified ${data.ok || 0}/${data.total || 0} packages`;
      if (data.issues?.length) msg += `, ${data.issues.length} issue${data.issues.length === 1 ? '' : 's'}`;
      Utils.makeToast(msg, data.issues?.length ? 'error' : 'success');
      if (data.issues?.length) {
        const el = document.getElementById('lock-content');
        let html = `<div class="card mt-4"><div class="card-title">Verification Issues</div>
          <div class="table-container"><table><thead><tr><th>Package</th><th>Issue</th><th>Severity</th></tr></thead><tbody>`;
        data.issues.forEach(i => {
          html += `<tr><td>${Utils.escapeHtml(i.name)}</td><td>${Utils.escapeHtml(i.issue)}</td><td>${Utils.severityBadge(i.severity)}</td></tr>`;
        });
        html += '</tbody></table></div></div>';
        el.insertAdjacentHTML('beforeend', html);
      }
    } catch (err) {
      Utils.makeToast(err.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'Verify';
  },

  async _checkOutdated() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    const btn = document.getElementById('lock-outdated');
    btn.disabled = true;
    btn.textContent = 'Checking...';
    try {
      const data = await api.getOutdated(this.state.lockData);
      const pkgs = data?.outdated_packages || data?.packages || [];
      if (pkgs.length === 0) {
        Utils.makeToast('All packages are up to date', 'success');
      } else {
        Utils.makeToast(`Found ${pkgs.length} outdated package${pkgs.length === 1 ? '' : 's'}`, 'info');
        const el = document.getElementById('lock-content');
        let html = `<div class="card mt-4"><div class="card-title">Outdated Packages</div>
          <div class="table-container"><table><thead><tr><th>Package</th><th>Current</th><th>Latest</th></tr></thead><tbody>`;
        pkgs.forEach(p => {
          html += `<tr><td>${Utils.escapeHtml(p.name || p.package || '?')}</td>
            <td class="version-cell">${Utils.escapeHtml(p.current_version || p.current || '?')}</td>
            <td class="version-cell">${Utils.escapeHtml(p.latest_version || p.latest || '?')}</td></tr>`;
        });
        html += '</tbody></table></div></div>';
        el.insertAdjacentHTML('beforeend', html);
      }
    } catch (err) {
      Utils.makeToast(err.message, 'error');
    }
    btn.disabled = false;
    btn.textContent = 'Check Outdated';
  },

  _exportLock() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    Utils.downloadFile(this.state.lockData, 'udr.lock');
    Utils.makeToast('Lock file exported', 'success');
  },

  _clearLock() {
    this.state.lockData = null;
    this.state.lockFileName = null;
    this.state.cveResults = null;
    this.state.licenseResults = null;
    document.getElementById('lock-content').innerHTML = `<div class="empty-state"><div class="icon">&#128196;</div><h3>No lock file loaded</h3><p>Drop a <code>udr.lock</code> file or click to browse.</p></div>`;
    Utils.makeToast('Lock file cleared', 'info');
    this._updateLockInfo();
    this._renderDashboard();
  },

  /* ====== CVE Check ====== */
  _renderCVE() {
    const el = document.getElementById('cve-results');
    if (!this.state.lockData) {
      el.innerHTML = `<div class="empty-state"><div class="icon">&#128737;</div><h3>No lock file loaded</h3><p>Drop a <code>udr.lock</code> file above to check for known vulnerabilities.</p></div>`;
    } else if (this.state.cveResults) {
      this._displayCVEResults();
    } else {
      el.innerHTML = `<p class="text-secondary">Lock file loaded: <strong>${Utils.escapeHtml(this.state.lockFileName)}</strong> (${Utils.getPackageCount(this.state.lockData)} packages). Click "Run CVE Check" to scan.</p>`;
    }
  },

  async _runCVE() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    const btn = document.getElementById('cve-run');
    const el = document.getElementById('cve-results');
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Querying OSV database...</span></div>';

    try {
      const pkgs = Utils.getPackagesFromLock(this.state.lockData);
      const vulns = await Utils.checkVulnerabilitiesOSV(pkgs);
      const licenses = Utils.checkLicenses(pkgs);
      this.state.cveResults = vulns;
      this.state.licenseResults = licenses;
      this._displayCVEResults();
      Utils.makeToast(`Found ${vulns.length} vulnerabilities`, vulns.length > 0 ? 'info' : 'success');
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><h3>Scan failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
    btn.disabled = false;
    btn.textContent = 'Run CVE Check';
  },

  _displayCVEResults() {
    const el = document.getElementById('cve-results');
    const vulns = this.state.cveResults || [];
    const critical = vulns.filter(v => v.severity === 'CRITICAL').length;
    const high = vulns.filter(v => v.severity === 'HIGH').length;
    const moderate = vulns.filter(v => v.severity === 'MODERATE').length;
    const low = vulns.filter(v => v.severity === 'LOW').length;

    let html = `<div class="lock-summary mb-4">
      <div class="lock-stat"><div class="num" style="color:var(--red)">${vulns.length}</div><div class="lbl">Total Vulns</div></div>
      <div class="lock-stat"><div class="num" style="color:var(--red)">${critical}</div><div class="lbl">Critical</div></div>
      <div class="lock-stat"><div class="num" style="color:var(--orange)">${high}</div><div class="lbl">High</div></div>
      <div class="lock-stat"><div class="num" style="color:var(--yellow)">${moderate}</div><div class="lbl">Moderate</div></div>
      <div class="lock-stat"><div class="num" style="color:var(--text-muted)">${low}</div><div class="lbl">Low</div></div>
    </div>`;

    if (vulns.length === 0) {
      html += `<div class="empty-state"><div class="icon">&#9989;</div><h3>No vulnerabilities found</h3></div>`;
    } else {
      html += '<div class="table-container"><table><thead><tr><th>Package</th><th>Version</th><th>Vulnerability</th><th>Severity</th><th>Fixed In</th></tr></thead><tbody>';
      vulns.sort((a, b) => {
        const order = { CRITICAL: 0, HIGH: 1, MODERATE: 2, LOW: 3 };
        return (order[a.severity] || 4) - (order[b.severity] || 4);
      });
      vulns.forEach(v => {
        html += `<tr>
          <td><strong>${Utils.escapeHtml(v.package)}</strong> ${Utils.ecoBadge(v.ecosystem)}</td>
          <td class="version-cell">${Utils.escapeHtml(v.version)}</td>
          <td><a href="https://osv.dev/${v.id}" target="_blank" title="${Utils.escapeHtml(v.summary)}">${Utils.escapeHtml(v.id)}</a><br><span class="text-muted text-sm">${Utils.truncate(v.summary, 80)}</span></td>
          <td>${Utils.severityBadge(v.severity)}</td>
          <td class="version-cell">${v.fixedVersion ? Utils.escapeHtml(v.fixedVersion) : '<span class="text-muted">—</span>'}</td>
        </tr>`;
      });
      html += '</tbody></table></div>';
    }

    el.innerHTML = html;

    if (this.state.licenseResults) {
      const el2 = document.getElementById('license-results');
      el2.innerHTML = this._renderLicenseTable(this.state.licenseResults);
    }
  },

  _renderLicenseTable(licenses) {
    const restricted = licenses.filter(l => l.status === 'restricted');
    const unknown = licenses.filter(l => l.status === 'unknown');
    let html = '';
    if (restricted.length) {
      html += `<h4 class="mb-2 mt-4">Restricted Licenses (${restricted.length})</h4>
      <div class="table-container"><table><thead><tr><th>Package</th><th>License</th><th>Status</th></tr></thead><tbody>`;
      restricted.forEach(l => {
        html += `<tr><td>${Utils.escapeHtml(l.package)}</td><td><span class="badge badge-red">${Utils.escapeHtml(l.license)}</span></td><td>${Utils.severityBadge('error')}</td></tr>`;
      });
      html += '</tbody></table></div>';
    }
    if (unknown.length) {
      html += `<h4 class="mb-2 mt-4">Unknown Licenses (${unknown.length})</h4>
      <div class="table-container"><table><thead><tr><th>Package</th><th>License</th><th>Status</th></tr></thead><tbody>`;
      unknown.forEach(l => {
        html += `<tr><td>${Utils.escapeHtml(l.package)}</td><td><span class="badge badge-yellow">${Utils.escapeHtml(l.license)}</span></td><td>${Utils.severityBadge('warning')}</td></tr>`;
      });
      html += '</tbody></table></div>';
    }
    if (!html) {
      html = `<p class="text-secondary mt-4"><span class="badge badge-green">All licenses approved</span></p>`;
    }
    return html;
  },

  /* ====== SBOM ====== */
  _renderSBOM() {
    const el = document.getElementById('sbom-content');
    if (!this.state.lockData) {
      el.innerHTML = `<div class="empty-state"><div class="icon">&#128203;</div><h3>No lock file loaded</h3><p>Drop a <code>udr.lock</code> file to generate an SBOM.</p></div>`;
    }
  },

  async _generateSBOM() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    const format = document.getElementById('sbom-format').value;
    const el = document.getElementById('sbom-output');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Generating SBOM...</span></div>';

    try {
      const content = Utils.generateSBOM(this.state.lockData, format);
      this.state.sbomContent = content;
      const size = (new Blob([content]).size / 1024).toFixed(1);
      el.innerHTML = `
        <p class="text-secondary mb-2">${format.toUpperCase()} SBOM generated (${size} KB)</p>
        <div class="btn-group mb-2">
          <button class="btn btn-sm btn-primary" onclick="App._downloadSBOM()">Download</button>
          <button class="btn btn-sm" onclick="App._copySBOM()">Copy</button>
        </div>
        <pre class="sbom-output">${Utils.escapeHtml(content)}</pre>
      `;
      Utils.makeToast('SBOM generated successfully', 'success');
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><h3>SBOM generation failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  _downloadSBOM() {
    const format = document.getElementById('sbom-format').value;
    const ext = format === 'spdx' ? 'spdx.json' : 'cyclonedx.json';
    Utils.downloadFile(this.state.sbomContent, `sbom.${ext}`, 'application/json');
    Utils.makeToast('SBOM downloaded', 'success');
  },

  _copySBOM() {
    navigator.clipboard.writeText(this.state.sbomContent).then(() => {
      Utils.makeToast('Copied to clipboard', 'success');
    }).catch(() => {
      Utils.makeToast('Failed to copy', 'error');
    });
  },

  /* ====== Policy Check ====== */
  _renderPolicy() {
    const el = document.getElementById('policy-results');
    if (this.state.policyResults) {
      this._displayPolicyResults();
    }
  },

  async _runPolicy() {
    if (!this.state.lockData) { Utils.makeToast('Load a lock file first', 'error'); return; }
    const yamlText = document.getElementById('policy-yaml').value.trim();
    if (!yamlText) { Utils.makeToast('Enter or upload a policy file', 'error'); return; }

    const el = document.getElementById('policy-results');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner"></div><span>Checking policy...</span></div>';

    try {
      const pkgs = Utils.getPackagesFromLock(this.state.lockData);
      const vulns = this.state.cveResults || await Utils.checkVulnerabilitiesOSV(pkgs);
      const licenses = Utils.checkLicenses(pkgs);
      this.state.cveResults = vulns;
      this.state.licenseResults = licenses;
      const violations = Utils.checkPolicy(pkgs, yamlText, vulns, licenses);
      this.state.policyResults = violations;
      this._displayPolicyResults();
      Utils.makeToast(`Found ${violations.length} policy violation${violations.length === 1 ? '' : 's'}`, violations.length > 0 ? 'error' : 'success');
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><h3>Policy check failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },

  _displayPolicyResults() {
    const el = document.getElementById('policy-results');
    const violations = this.state.policyResults || [];
    const errors = violations.filter(v => v.severity === 'error');
    const warnings = violations.filter(v => v.severity === 'warning');

    let html = `<div class="lock-summary mb-4">
      <div class="lock-stat"><div class="num" style="color:${errors.length ? 'var(--red)' : 'var(--green)'}">${errors.length}</div><div class="lbl">Errors</div></div>
      <div class="lock-stat"><div class="num" style="color:${warnings.length ? 'var(--yellow)' : 'var(--text-muted)'}">${warnings.length}</div><div class="lbl">Warnings</div></div>
    </div>`;

    if (violations.length === 0) {
      html += `<div class="empty-state"><div class="icon">&#9989;</div><h3>All policy checks passed</h3></div>`;
    } else {
      html += '<div class="table-container"><table><thead><tr><th>Package</th><th>Rule</th><th>Message</th><th>Severity</th></tr></thead><tbody>';
      violations.forEach(v => {
        html += `<tr>
          <td><strong>${Utils.escapeHtml(v.package)}</strong></td>
          <td><span class="badge badge-blue">${Utils.escapeHtml(v.rule)}</span></td>
          <td class="text-sm">${Utils.escapeHtml(v.message)}</td>
          <td>${Utils.severityBadge(v.severity)}</td>
        </tr>`;
      });
      html += '</tbody></table></div>';
    }

    el.innerHTML = html;
  },

  /* ====== System Info ====== */
  async _renderSystemInfo(force = false) {
    const el = document.getElementById('system-content');
    el.innerHTML = '<div class="loading-overlay"><div class="spinner spinner-lg"></div><span>Scanning system...</span></div>';

    try {
      const data = force ? await api.getSystemInfo(true) : (this.state.cachedSystemInfo || await api.getSystemInfo(true));
      if (!force) this.state.cachedSystemInfo = data;

      const info = data?.data || {};
      const platform = info.platform || {};
      const cpu = info.cpu || {};
      const gpu = info.gpu || {};
      const mem = info.memory || {};
      const python = info.runtime_versions?.python || {};
      const disks = info.disks || [];

      el.innerHTML = `
        <div class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">OS</div>
            <div class="stat-value" style="font-size:1.1rem">${platform.system || 'Unknown'}</div>
            <div class="stat-sub">${platform.release || ''} ${platform.machine || ''}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">CPU</div>
            <div class="stat-value" style="font-size:1rem">${cpu.brand || cpu.model || 'Unknown'}</div>
            <div class="stat-sub">${cpu.cores || cpu.physical_cores || '?'} cores</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">Memory</div>
            <div class="stat-value" style="font-size:1.2rem">${mem.total_gb ? mem.total_gb.toFixed(1) + ' GB' : '—'}</div>
            <div class="stat-sub">${mem.available_gb ? mem.available_gb.toFixed(1) + ' GB available' : ''}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">GPU</div>
            <div class="stat-value" style="font-size:1rem">${gpu.available ? (gpu.devices?.[0]?.name || 'Available') : 'Not detected'}</div>
            <div class="stat-sub">${gpu.cuda ? 'CUDA ' + gpu.cuda : ''}</div>
          </div>
        </div>

        <div class="card">
          <div class="card-title">Python</div>
          <div class="info-grid">
            <span class="label">Version</span><span class="value">${python.version || '—'}</span>
            <span class="label">Path</span><span class="value">${python.executable || python.path || '—'}</span>
            <span class="label">Packages</span><span class="value">${(info.python_packages || info.packages || []).length || '—'}</span>
          </div>
        </div>

        <div class="card">
          <div class="card-title">GPU Details</div>
          ${gpu.available ? `
          <div class="table-container"><table><thead><tr><th>Device</th><th>Memory</th><th>Driver</th></tr></thead><tbody>
            ${(gpu.devices || []).map(d => `<tr>
              <td>${Utils.escapeHtml(d.name || 'Unknown')}</td>
              <td>${d.memory_mb ? (d.memory_mb / 1024).toFixed(1) + ' GB' : '—'}</td>
              <td>${Utils.escapeHtml(d.driver || d.driver_version || '—')}</td>
            </tr>`).join('')}
          </tbody></table></div>
          ` : `<p class="text-secondary">No GPU detected</p>`}
        </div>

        <div class="card">
          <div class="card-title">System Capabilities</div>
          <div class="info-grid">
            <span class="label">Hostname</span><span class="value">${info.hostname || '—'}</span>
            <span class="label">Docker</span><span class="value">${info.docker?.available ? '<span class="badge badge-green">Available</span>' : '<span class="badge badge-yellow">Not found</span>'}</span>
            <span class="label">Rust</span><span class="value">${info.rust?.available ? '<span class="badge badge-green">' + Utils.escapeHtml(info.rust.rustc || '') + '</span>' : '<span class="badge badge-yellow">Not found</span>'}</span>
            <span class="label">Go</span><span class="value">${info.go?.available ? '<span class="badge badge-green">' + Utils.escapeHtml(info.go.version || '') + '</span>' : '<span class="badge badge-yellow">Not found</span>'}</span>
            <span class="label">Ruby</span><span class="value">${info.ruby?.available ? '<span class="badge badge-green">Available</span>' : '<span class="badge badge-yellow">Not found</span>'}</span>
          </div>
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><div class="icon">&#9888;</div><h3>System scan failed</h3><p>${Utils.escapeHtml(err.message)}</p></div>`;
    }
  },
};

document.addEventListener('DOMContentLoaded', () => App.init());
