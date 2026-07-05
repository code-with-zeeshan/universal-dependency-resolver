// ===================== State =====================
let BASE = 'http://127.0.0.1:8199'
let lastResolved = JSON.parse(sessionStorage.getItem('udr_lastResolved') || 'null')
let lastScanData = null
let exportFormats = []
let sysInfoCache = null
let sysInfoCacheTime = 0
const SYS_CACHE_TTL = 30000

// Settings persistence
function loadSetting(key, def) {
  try { const v = localStorage.getItem('udr_' + key); return v !== null ? JSON.parse(v) : def } catch(e) { return def }
}
function saveSetting(key, val) {
  try { localStorage.setItem('udr_' + key, JSON.stringify(val)) } catch(e) {}
}

// Toast notification system
function showToast(msg, type = 'info', duration = 4000) {
  const c = document.getElementById('toastContainer')
  const el = document.createElement('div')
  el.className = 'toast ' + type
  el.innerHTML = '<span>' + msg + '</span><span class="close-btn" onclick="this.parentElement.remove()">✕</span>'
  c.appendChild(el)
  if (duration > 0) setTimeout(() => { el.style.animation = 'toastOut .25s ease forwards'; setTimeout(() => el.remove(), 300) }, duration)
}

// Loading overlay
let loadingCount = 0
function showLoading(msg, sub) {
  loadingCount++
  document.getElementById('loadingMsg').textContent = msg || 'Loading...'
  document.getElementById('loadingSub').textContent = sub || ''
  document.getElementById('loadingOverlay').classList.add('show')
}
function hideLoading() {
  loadingCount = Math.max(0, loadingCount - 1)
  if (loadingCount === 0) document.getElementById('loadingOverlay').classList.remove('show')
}

// Error boundary wrapper — wraps an async operation with loading + error handling
async function withErrorBoundary(tabId, fn) {
  const tab = document.getElementById('tab-' + tabId)
  if (!tab) return fn()
  try {
    const result = await fn()
    return result
  } catch(e) {
    // Find the first result card or show in a new error card
    let errorEl = tab.querySelector('.error-boundary') || tab.querySelector('.card:last-child')
    if (errorEl) {
      errorEl.innerHTML = errorEl.innerHTML + '<div class="alert error" style="margin-top:8px">⚠ ' + e.message + ' <button class="ghost" onclick="this.parentElement.remove()" style="font-size:11px">✕</button></div>'
    }
    showToast(e.message, 'error', 6000)
    throw e
  }
}

async function getBaseUrl() {
  if (window.udrDesktop) {
    try { BASE = await window.udrDesktop.getBackendUrl() || BASE } catch(e) {}
  } else if (window.__UDR_BACKEND_URL__) {
    BASE = window.__UDR_BACKEND_URL__
  }
}
getBaseUrl()

if (window.udrDesktop && window.udrDesktop.onBackendReady) {
  window.udrDesktop.onBackendReady(async () => {
    if (window.udrDesktop) {
      try { BASE = await window.udrDesktop.getBackendUrl() || BASE } catch(e) {}
    }
    document.title = 'UDR'
    setStatus(true, 'Backend ready')
    document.getElementById('dashStatus').textContent = 'Healthy'
    await populateAllEcosystemSelects()
    loadSystemInfo()
    loadExportFormats()
  })
}

function setStatus(ok, msg) {
  const cls = ok === true ? 'green' : ok === false ? 'red' : 'yellow'
  document.getElementById('statusDot').className = 'status-dot ' + cls
  document.getElementById('statusText').textContent = msg
}

const DEFAULT_API_TIMEOUT = 15000
const LONG_API_TIMEOUT = 120000

let activeController = null

function abortActiveRequest() {
  if (activeController) {
    activeController.abort()
    activeController = null
  }
}

let apiCallCount = 0

function showCancelButton(show) {
  const btn = document.getElementById('cancelBtn')
  if (btn) {
    if (show) { apiCallCount++; btn.style.display = 'inline-flex' }
    else { apiCallCount = Math.max(0, apiCallCount - 1); if (apiCallCount === 0) btn.style.display = 'none' }
  }
}

async function api(method, path, body, timeoutMs = DEFAULT_API_TIMEOUT) {
  abortActiveRequest()
  const controller = new AbortController()
  activeController = controller
  showCancelButton(true)
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  const opts = {method,headers:{'Content-Type':'application/json'},signal:controller.signal}
  if(body) opts.body = JSON.stringify(body)
  let r
  try {
    r = await fetch(BASE + path, opts)
  } catch(e) {
    clearTimeout(timeout)
    if (activeController === controller) { activeController = null; showCancelButton(false) }
    if (e.name === 'AbortError') throw new Error(e.message.includes('aborted') && !e.message.includes('timeout') ? 'Request cancelled' : `Request timed out after ${timeoutMs/1000}s`)
    throw e
  }
  clearTimeout(timeout)
  if (activeController === controller) { activeController = null; showCancelButton(false) }
  if (!r.ok) {
    let detail = r.statusText
    try { const j = await r.json(); detail = j.detail || detail } catch(e) {}
    throw new Error(detail)
  }
  return r.json()
}

async function apiWithError(path, body, timeoutMs = DEFAULT_API_TIMEOUT) {
  const btn = event.target
  const wasText = btn.innerHTML
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Working...'
  try {
    const r = await api('POST', path, body, timeoutMs)
    btn.disabled = false; btn.innerHTML = wasText
    return r
  } catch(e) {
    btn.disabled = false; btn.innerHTML = wasText
    throw e
  }
}

function showError(msg, el) {
  if (el) el.innerHTML = `<div class="alert error">${msg}</div>`
  else console.error(msg)
}

function showSuccess(msg, el) {
  if (el) el.innerHTML = `<div class="alert success">${msg}</div>`
}

function showWarning(msg, el) {
  if (el) el.innerHTML = `<div class="alert warning">${msg}</div>`
}

function updateTrayStatus(data) {
  if (window.udrDesktop && window.udrDesktop.send) {
    window.udrDesktop.send('update-tray-status', data)
  }
}

function toggleRaw(id) {
  const el = document.getElementById(id)
  el.style.display = el.style.display === 'none' ? 'block' : 'none'
}

function toggleHelpModal() {
  const el = document.getElementById('helpModal')
  el.style.display = el.style.display === 'none' ? 'flex' : 'none'
}

function switchTab(name) {
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name))
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.id === 'tab-' + name))
}

function openPackageDetails(name, ecosystem) {
  document.getElementById('detPkgInput').value = name
  if (ecosystem) document.getElementById('detEcoSelect').value = ecosystem
  switchTab('details')
  document.getElementById('detBtn').click()
}

document.getElementById('tabNav').addEventListener('click', e => {
  const btn = e.target.closest('.nav-btn')
  if (btn) switchTab(btn.dataset.tab)
})

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault()
    switchTab('resolve')
    document.getElementById('pkgInput').focus()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
    e.preventDefault()
    switchTab('scan')
    document.getElementById('scanPath').focus()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'l') {
    e.preventDefault()
    switchTab('restore')
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'q') {
    e.preventDefault()
    if (window.udrDesktop && window.udrDesktop.quit) window.udrDesktop.quit()
  }
  if (e.key === '?' && !e.ctrlKey && !e.metaKey && !e.target.closest('input,textarea,select')) {
    e.preventDefault()
    toggleHelpModal()
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
    const active = document.activeElement
    if (active && active.closest('.tab.active')) {
      const btn = active.closest('.tab.active').querySelector('button:not(.ghost):not(.secondary)')
      if (btn) btn.click()
    }
  }
})

// ===================== Formatting Helpers =====================

function formatResolveTable(resolved) {
  const pkgs = resolved.resolved_packages || {}
  const names = Object.keys(pkgs)
  if (!names.length) return '<div class="alert warning">No packages resolved</div>'
  let h = '<table class="result-table"><tr><th>Package</th><th>Ecosystem</th><th>Version</th><th>Notes</th></tr>'
  for (const name of names) {
    const info = pkgs[name]
    const cuda = info.cuda_version ? `CUDA ${info.cuda_version}` : ''
    h += `<tr><td><strong>${name}</strong></td><td><span class="badge blue">${info.ecosystem||'-'}</span></td><td><span class="badge green">${info.version||'?'}</span></td><td>${cuda}</td></tr>`
  }
  h += '</table>'
  const status = resolved.status
  if (status === 'satisfiable') h = '<div class="alert success">All dependencies resolved successfully</div>' + h
  else if (status === 'unsatisfiable') h = '<div class="alert warning">Some dependencies could not be satisfied</div>' + h
  if (resolved.warnings && resolved.warnings.length) {
    h += '<div style="margin-top:8px;font-size:12px;color:var(--yellow)">' + resolved.warnings.map(w => '⚠ ' + w).join('<br>') + '</div>'
  }
  return h
}

function formatSearchResults(data) {
  const results = data.results || data
  const keys = Object.keys(results)
  if (!keys.length) return '<div class="alert warning">No results found</div>'
  let h = `<div class="alert success">Found ${data.total_count || '?'} results</div>`
  for (const eco of keys) {
    const items = results[eco]
    if (!items || !items.length) continue
    h += `<h3 style="font-size:13px;margin:10px 0 4px;color:var(--accent-light)">${eco}</h3>`
    h += '<table class="result-table"><tr><th>Name</th><th>Version</th><th>Description</th></tr>'
    for (const item of items) {
      const pkgName = item.name || item
      h += `<tr style="cursor:pointer" onclick="openPackageDetails('${pkgName}','${eco}')" title="View details for ${pkgName}"><td><strong>${pkgName}</strong></td><td>${item.version||'-'}</td><td style="color:var(--text-muted)">${(item.description||'').substring(0,80)}</td></tr>`
    }
    h += '</table>'
  }
  return h
}

function formatVersions(data) {
  const info = data.data || data
  const eco = info.ecosystem || Object.keys(info.versions || {})[0] || 'pypi'
  const versions = info.versions ? (info.versions[eco] || []) : []
  if (!versions.length) return '<div class="alert warning">No versions found</div>'
  let h = `<div class="alert success">${versions.length} versions available</div>`
  h += '<table class="result-table"><tr><th>Version</th><th>Published</th><th>Python Requires</th></tr>'
  for (const v of versions) {
    const ver = typeof v === 'string' ? v : v.version
    const date = v.release_date ? new Date(v.release_date).toLocaleDateString() : '-'
    const py = v.python_requires || '-'
    h += `<tr><td><span class="badge green">${ver}</span></td><td>${date}</td><td>${py}</td></tr>`
  }
  h += '</table>'
  return h
}

function formatDependencies(data, eco) {
  const deps = data.dependencies ? data.dependencies[eco] : data
  const all = deps && deps.all ? deps.all : []
  if (!all.length) return '<div class="alert warning">No dependencies found</div>'
  let h = `<div class="alert success">${all.length} dependencies</div>`
  h += '<table class="result-table"><tr><th>Package</th><th>Version Spec</th><th>Optional</th></tr>'
  for (const d of all) {
    const name = d.name || d
    const spec = d.version_spec || d.requirement || '*'
    const opt = d.optional ? 'Yes' : 'No'
    h += `<tr><td><strong>${name}</strong></td><td><span class="badge blue">${spec}</span></td><td>${opt}</td></tr>`
  }
  h += '</table>'
  return h
}

function formatCompatibility(data) {
  const compat = data.compatibility_matrix || data.compatibility || data
  if (!compat || !Object.keys(compat).length) return '<div class="alert warning">No compatibility information available</div>'
  let h = '<table class="result-table"><tr><th>Constraint</th><th>Status</th><th>Note</th></tr>'
  for (const [key, val] of Object.entries(compat)) {
    const ok = val && val.compatible !== false
    h += `<tr><td>${key}</td><td><span class="badge ${ok?'green':'red'}">${ok?'Compatible':'Incompatible'}</span></td><td>${val.note||val.message||'-'}</td></tr>`
  }
  h += '</table>'
  return h
}

function formatScanResult(result) {
  const status = result.status
  if (status === 'no_manifests') return '<div class="alert warning">No manifest files found in the project directory</div>'
  if (status === 'no_packages') return '<div class="alert warning">No packages found in manifests</div>'
  let h = '<div class="alert success">Project scanned successfully</div>'
  if (result.manifests && result.manifests.length) {
    h += '<h3 style="font-size:13px;margin:8px 0;color:var(--accent-light)">Detected Manifests</h3>'
    h += '<table class="result-table"><tr><th>File</th><th>Ecosystem</th></tr>'
    for (const m of result.manifests) h += `<tr><td>${m.filename}</td><td><span class="badge blue">${m.ecosystem}</span></td></tr>`
    h += '</table>'
  }
  if (result.packages && result.packages.length) {
    h += '<h3 style="font-size:13px;margin:8px 0;color:var(--accent-light)">Resolved Packages</h3>'
    h += '<table class="result-table"><tr><th>Package</th><th>Ecosystem</th><th>Constraint</th><th>Resolved</th><th>Notes</th></tr>'
    for (const p of result.packages) {
      const ver = p.resolved_version ? `<span class="badge green">${p.resolved_version}</span>` : '<span class="badge red">unresolved</span>'
      const cuda = p.cuda_variant ? `CUDA ${p.cuda_version}` : ''
      h += `<tr><td><strong>${p.name}</strong></td><td><span class="badge blue">${p.ecosystem}</span></td><td>${p.constraint}</td><td>${ver}</td><td>${cuda}</td></tr>`
    }
    h += '</table>'
  }
  if (result.system) {
    h += '<h3 style="font-size:13px;margin:8px 0;color:var(--accent-light)">System</h3>'
    h += '<div class="info-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">'
    for (const [k,v] of Object.entries(result.system)) {
      h += `<div class="info-item"><div class="label">${k}</div><div class="value">${v||'-'}</div></div>`
    }
    h += '</div>'
  }
  return h
}

function formatGraphTree(trees) {
  if (!trees || !trees.length) return '<div class="alert warning">No dependency tree available</div>'
  function renderNode(node) {
    let h = `<div class="tree-node"><strong>${node.name}</strong><span class="ver">${node.version}</span><span class="eco">(${node.ecosystem})</span></div>`
    if (node.children && node.children.length) {
      h += '<div class="tree-children">'
      for (const child of node.children) h += renderNode(child)
      h += '</div>'
    }
    return h
  }
  let h = ''
  for (const tree of trees) h += renderNode(tree)
  return h
}

function formatVerifyResult(data) {
  const total = data.total || 0
  const ok = data.ok || 0
  const issues = data.issues || []
  let h = `<div class="alert ${issues.length ? (issues.some(i=>i.severity==='error')?'warning':'success') : 'success'}">`
  h += `${ok}/${total} packages verified successfully`
  if (issues.length) h += ` — ${issues.length} issue(s) found`
  h += '</div>'
  if (issues.length) {
    h += '<table class="result-table"><tr><th>Severity</th><th>Package</th><th>Issue</th></tr>'
    for (const iss of issues) {
      const sev = iss.severity === 'error' ? '<span class="badge red">ERROR</span>' : '<span class="badge yellow">WARN</span>'
      h += `<tr><td>${sev}</td><td><strong>${iss.name}</strong></td><td>${iss.issue}</td></tr>`
    }
    h += '</table>'
  }
  return h
}

function formatUpdateResult(data) {
  if (data.updated) {
    return `<div class="alert success"><strong>${data.package}</strong> updated: ${data.old_version} → ${data.new_version}</div>`
  } else {
    return `<div class="alert success">${data.package} is already at ${data.new_version} — no update needed</div>`
  }
}

// ===================== Ecosystem Loading =====================

let ECOSYSTEMS = []
async function loadEcosystems() {
  try {
    const res = await api('GET', '/api/v1/packages/ecosystems')
    const ecoData = res.ecosystems || res.data || res
    if (Array.isArray(ecoData)) {
      ECOSYSTEMS = ecoData.map(e => [typeof e === 'string' ? e : (e.id || e.name || e), typeof e === 'string' ? e : (e.name || e.id || e)])
    } else if (typeof ecoData === 'object' && ecoData !== null) {
      ECOSYSTEMS = Object.keys(ecoData).map(k => [k, ecoData[k].name || k])
    }
  } catch(e) {}
  if (!ECOSYSTEMS.length) {
    ECOSYSTEMS = [
      ['pypi','PyPI (Python)'],['conda','Conda'],['npm','NPM (Node.js)'],
      ['crates','Crates.io (Rust)'],['maven','Maven (Java)'],['gomodules','Go Modules'],
      ['apt','APT (Debian)'],['apk','APK (Alpine)'],['cocoapods','CocoaPods (iOS)'],
      ['homebrew','Homebrew (macOS)'],['nuget','NuGet (.NET)'],['packagist','Packagist (PHP)'],
      ['rubygems','RubyGems'],['gradle','Gradle (Groovy/Kotlin)'],['swift','Swift Package Manager'],
      ['hex','Hex (Elixir/Erlang)'],['haskell','Hackage (Haskell/Cabal)']
    ]
  }
}

function populateSelect(id, items) {
  const sel = document.getElementById(id)
  sel.innerHTML = items.map(([v,l]) => `<option value="${v}">${l}</option>`).join('')
}

async function populateAllEcosystemSelects() {
  await loadEcosystems()
  const allWithEmpty = [['','All ecosystems'], ...ECOSYSTEMS]
  for (const id of ['ecoSelect','detEcoSelect','verEcoSelect','depEcoSelect','comEcoSelect','graphEcoSelect']) {
    populateSelect(id, ECOSYSTEMS)
  }
  populateSelect('searchEco', allWithEmpty)
}

async function loadExportFormats() {
  try {
    const res = await api('GET', '/api/v1/packages/export-formats')
    exportFormats = res.formats || []
    const sel = document.getElementById('exportFormatSelect')
    sel.innerHTML = '<option value="">Select format...</option>' + exportFormats.map(f =>
      `<option value="${f.format}">${f.format} — ${f.description}</option>`
    ).join('')
    const sel2 = document.getElementById('scanExportFmt')
    sel2.innerHTML = '<option value="">No export</option>' + exportFormats.map(f =>
      `<option value="${f.format}">${f.format} — ${f.description}</option>`
    ).join('')
  } catch(e) {
    console.warn('Failed to load export formats:', e.message)
    exportFormats = [
      {format:'requirements.txt',description:'pip requirements.txt'},
      {format:'pyproject.toml',description:'PEP 621 pyproject.toml'},
    ]
    const sel = document.getElementById('exportFormatSelect')
    sel.innerHTML = '<option value="">Select format...</option>' + exportFormats.map(f =>
      `<option value="${f.format}">${f.format} — ${f.description}</option>`
    ).join('')
    const sel2 = document.getElementById('scanExportFmt')
    sel2.innerHTML = '<option value="">No export</option>' + exportFormats.map(f =>
      `<option value="${f.format}">${f.format} — ${f.description}</option>`
    ).join('')
  }
}

// ===================== Bootstrap =====================

async function init() {
  setStatus(null, 'connecting...')
  // Restore saved settings
  const savedDir = loadSetting('lastDir', '')
  const dirInput = document.getElementById('scanPath')
  if (dirInput && savedDir) dirInput.value = savedDir
  try {
    const health = await api('GET', '/api/v1/health')
    setStatus(true, 'connected')
    const root = await api('GET', '/')
    document.getElementById('dashStatus').textContent = 'Healthy'
    const version = root.version || health.version || '-'
    document.getElementById('dashVersion').textContent = version
    document.getElementById('dashMode').textContent = root.mode || health.mode || 'local'
    await populateAllEcosystemSelects()
    document.getElementById('dashEco').textContent = ECOSYSTEMS.length + ' available'
    await loadExportFormats()
    loadSystemInfo()
    updateTrayStatus({ version, backendStatus: 'running' })
    showToast('Backend connected — ' + version, 'success', 3000)
  } catch(e) {
    setStatus(false, 'disconnected')
    document.getElementById('dashStatus').innerHTML = 'Disconnected <button class="ghost" onclick="init()" style="font-size:11px">Retry</button>'
  }
}

let sysLoading = false
async function loadSystemInfo(force) {
  if (sysLoading) return
  const now = Date.now()
  if (!force && sysInfoCache && (now - sysInfoCacheTime) < SYS_CACHE_TTL) {
    renderSystemInfo(sysInfoCache)
    return
  }
  sysLoading = true
  const grid = document.getElementById('sysInfoGrid')
  const pre = document.getElementById('runtimePre')
  grid.innerHTML = '<div class="loading-state"><span class="spinner"></span>Loading system info...</div>'
  try {
    const info = await api('GET', '/api/v1/system/info')
    sysInfoCache = info
    sysInfoCacheTime = now
    renderSystemInfo(info)
  } catch(e) {
    grid.innerHTML = `<div class="info-item"><div class="label">Error</div><div class="value bad">${e.message}</div></div>`
    pre.textContent = 'Error: ' + e.message
  }
  sysLoading = false
}

function renderSystemInfo(info) {
  const grid = document.getElementById('sysInfoGrid')
  const pre = document.getElementById('runtimePre')
  const s = info.system || info.data || {}
  grid.innerHTML = [
    ['OS', s.os || '-', 'good'],
    ['CPU', s.cpu || '-', 'good'],
    ['GPU', s.gpu || 'None detected', s.gpu ? 'good' : 'warn'],
    ['CUDA', s.cuda || 'Not available', s.cuda ? 'good' : 'warn'],
    ['Python', s.python || '-', 'good'],
  ].map(([l,v,cls]) =>
    `<div class="info-item"><div class="label">${l}</div><div class="value ${cls}">${v}</div></div>`
  ).join('')
  pre.textContent = JSON.stringify(info, null, 2)
}

// ===================== Event Handlers =====================

// --- Resolve ---
document.getElementById('resolveBtn').addEventListener('click', async () => {
  await withErrorBoundary('resolve', async () => {
    const raw = document.getElementById('pkgInput').value.trim()
    if(!raw) return
    const eco = document.getElementById('ecoSelect').value
    const packages = raw.split(/\s+/).map(p => {
      if(p.includes('@')) { const [name, e] = p.split('@'); return {name, ecosystem: e} }
      return {name: p, ecosystem: eco}
    })
    const btn = document.getElementById('resolveBtn')
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Resolving...'
    const card = document.getElementById('resolveResultCard')
    const div = document.getElementById('resolveResult')
    card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Running SAT solver...</div>'
    showLoading('Resolving dependencies...', packages.length + ' package(s)')
    try {
      const device = document.getElementById('resolveDeviceSelect').value
      const body = {packages}
      if (device === 'cuda12.1') body.system_info = {gpu: {available: true, cuda: '12.1'}}
      else if (device === 'cuda11.8') body.system_info = {gpu: {available: true, cuda: '11.8'}}
      else if (device === 'cpu') body.system_info = {gpu: {available: false, cuda: ''}}
      else if (device === 'mps') body.system_info = {gpu: {available: true, type: 'mps', cuda: ''}}
      const result = await api('POST', '/api/v1/packages/resolve', body, LONG_API_TIMEOUT)
      lastResolved = result
      sessionStorage.setItem('udr_lastResolved', JSON.stringify(result))
      div.innerHTML = formatResolveTable(result)
      document.getElementById('resolveRaw').textContent = JSON.stringify(result, null, 2)
      document.getElementById('exportLastBtn').disabled = false
      updateTrayStatus({ lastResolved: new Date().toLocaleTimeString() })
      const count = Object.keys(result.resolved_packages || {}).length
      showToast(`Resolved ${count} packages`, 'success')
    } catch(e) {
      showError(e.message, div)
      showToast(e.message, 'error', 6000)
    }
    btn.disabled = false; btn.textContent = 'Resolve'
    hideLoading()
  })
})

// --- Export (merged into Resolve tab) ---
document.getElementById('exportLastBtn').addEventListener('click', async () => {
  const fmt = document.getElementById('exportFormatSelect').value
  if (!fmt) { showWarning('Select an export format first', document.getElementById('exportResultPre')); document.getElementById('exportResultCard').style.display = 'block'; return }
  const resolvedData = lastResolved ? (lastResolved.data || lastResolved) : null
  if (!resolvedData) {
    document.getElementById('exportResultCard').style.display = 'block'
    document.getElementById('exportResultPre').textContent = 'No resolution results yet. Go to Resolve tab first.'
    return
  }
  const btn = document.getElementById('exportLastBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Exporting...'
  const card = document.getElementById('exportResultCard')
  const el = document.getElementById('exportResultPre')
  card.style.display = 'block'; el.textContent = 'Exporting...'
  try {
    const result = await api('POST', '/api/v1/packages/export', {format: fmt, resolved_packages: resolvedData})
    el.textContent = result.content || JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, el)
  }
  btn.disabled = false; btn.innerHTML = 'Export'
})

// --- Search ---
document.getElementById('searchBtn').addEventListener('click', async () => {
  const q = document.getElementById('searchInput').value.trim()
  if(!q) return
  const eco = document.getElementById('searchEco').value
  const btn = document.getElementById('searchBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Searching...'
  const card = document.getElementById('searchResultCard')
  const div = document.getElementById('searchResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Searching...</div>'
  try {
    const params = new URLSearchParams({q})
    if(eco) params.set('ecosystems', eco)
    const result = await api('GET', '/api/v1/packages/search?' + params.toString())
    div.innerHTML = formatSearchResults(result)
    document.getElementById('searchRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Search'
})

// --- Details ---
document.getElementById('detBtn').addEventListener('click', async () => {
  const name = document.getElementById('detPkgInput').value.trim()
  if(!name) return
  const eco = document.getElementById('detEcoSelect').value
  const btn = document.getElementById('detBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Loading...'
  const card = document.getElementById('detResultCard')
  const div = document.getElementById('detResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Fetching details...</div>'
  try {
    const result = await api('GET', `/api/v1/packages/${eco}/${name}/details`)
    const d = result.data || result
    div.innerHTML = `<div class="alert success">${name} — ${eco}</div>
      <div class="info-grid" style="grid-template-columns:repeat(auto-fill,minmax(200px,1fr))">
        <div class="info-item"><div class="label">Name</div><div class="value">${d.name||name}</div></div>
        <div class="info-item"><div class="label">Ecosystem</div><div class="value"><span class="badge blue">${d.ecosystem||eco}</span></div></div>
        <div class="info-item"><div class="label">Latest Version</div><div class="value"><span class="badge green">${d.latest_version||d.version||'-'}</span></div></div>
      </div>`
    if (d.description) div.innerHTML += `<p style="font-size:13px;color:var(--text-muted);margin-top:8px">${d.description}</p>`
    document.getElementById('detRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Get Details'
})

// --- Versions ---
document.getElementById('verBtn').addEventListener('click', async () => {
  const name = document.getElementById('verPkgInput').value.trim()
  if(!name) return
  const eco = document.getElementById('verEcoSelect').value
  const btn = document.getElementById('verBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Loading...'
  const card = document.getElementById('verResultCard')
  const div = document.getElementById('verResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Fetching versions...</div>'
  try {
    const result = await api('GET', `/api/v1/packages/${eco}/${name}/versions`)
    div.innerHTML = formatVersions(result)
    document.getElementById('verRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'List Versions'
})

// --- Dependencies ---
document.getElementById('depBtn').addEventListener('click', async () => {
  const name = document.getElementById('depPkgInput').value.trim()
  if(!name) return
  const eco = document.getElementById('depEcoSelect').value
  const btn = document.getElementById('depBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Loading...'
  const card = document.getElementById('depResultCard')
  const div = document.getElementById('depResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Fetching dependencies...</div>'
  try {
    const result = await api('GET', `/api/v1/packages/${eco}/${name}/dependencies`)
    div.innerHTML = formatDependencies(result, eco)
    document.getElementById('depRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'View Dependencies'
})

// --- Compatibility ---
document.getElementById('comBtn').addEventListener('click', async () => {
  const name = document.getElementById('comPkgInput').value.trim()
  if(!name) return
  const eco = document.getElementById('comEcoSelect').value
  const btn = document.getElementById('comBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Loading...'
  const card = document.getElementById('comResultCard')
  const div = document.getElementById('comResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Checking compatibility...</div>'
  try {
    const result = await api('GET', `/api/v1/packages/${eco}/${name}/compatibility`)
    div.innerHTML = formatCompatibility(result)
    document.getElementById('comRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Check Compatibility'
})

// --- System ---
document.getElementById('refreshSysBtn').addEventListener('click', () => loadSystemInfo(true))
document.getElementById('checkCompatBtn').addEventListener('click', async () => {
  const div = document.getElementById('sysCompatResult')
  div.style.display = 'block'
  div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Checking compatibility...</div>'
  try {
    const info = await api('GET', '/api/v1/system/info')
    const result = await api('POST', '/api/v1/system/check-compatibility', {system: info.system || info.data || {}})
    const checks = result.checks || result.results || []
    if (checks.length) {
      let h = '<table class="result-table"><tr><th>Check</th><th>Status</th><th>Detail</th></tr>'
      for (const c of checks) {
        const ok = c.status === 'pass' || c.status === 'ok'
        h += `<tr><td>${c.name||c.type||'?'}</td><td><span class="badge ${ok?'green':'red'}">${c.status}</span></td><td>${c.message||c.detail||'-'}</td></tr>`
      }
      h += '</table>'
      div.innerHTML = h
    } else {
      div.innerHTML = '<div class="alert success">System compatibility check complete</div>'
    }
  } catch(e) {
    div.innerHTML = `<div class="alert error">${e.message}</div>`
  }
})

// --- Scan ---
document.getElementById('scanModeNav').addEventListener('click', e => {
  const btn = e.target.closest('button')
  if (!btn) return
  document.querySelectorAll('#scanModeNav button').forEach(b => b.classList.remove('active'))
  btn.classList.add('active')
  const mode = btn.dataset.mode
  document.getElementById('scanLocal').style.display = mode === 'local' ? 'block' : 'none'
  document.getElementById('scanGithub').style.display = mode === 'github' ? 'block' : 'none'
  document.getElementById('scanUpload').style.display = mode === 'upload' ? 'block' : 'none'
})

document.getElementById('browseBtn').addEventListener('click', async () => {
  if (window.udrDesktop) {
    const dir = await window.udrDesktop.selectDirectory()
    if (dir) document.getElementById('scanPath').value = dir
  } else {
    document.getElementById('scanPath').value = prompt('Enter directory path:')
  }
})

async function doScan(path, body, source) {
  const exportFmt = document.getElementById('scanExportFmt').value
  const card = document.getElementById('scanResultCard')
  const div = document.getElementById('scanResult')
  document.getElementById('scanLockRow').style.display = 'none'
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Detecting manifests and resolving...</div>'
  showLoading('Scanning project...', source === 'local' ? body.directory_path : body.repo_url || '')
  try {
    let url = `/api/v1/scan/${source}`
    if (exportFmt) url += `?export=${encodeURIComponent(exportFmt)}`
    const result = await api('POST', url, body, LONG_API_TIMEOUT)
    lastScanData = result
    div.innerHTML = formatScanResult(result)
    document.getElementById('scanRaw').textContent = JSON.stringify(result, null, 2)
    if (result.export) {
      document.getElementById('scanResultExport').style.display = 'block'
      document.getElementById('scanExportContent').textContent = result.export
    }
    if (result.packages && result.packages.length) {
      document.getElementById('scanLockRow').style.display = 'flex'
      document.getElementById('scanLockMsg').textContent = `${result.packages.length} packages resolved`
      lastResolved = {resolved_packages: {}}
      for (const p of result.packages) {
        lastResolved.resolved_packages[p.name] = {version: p.resolved_version, ecosystem: p.ecosystem, cuda_variant: p.cuda_variant, cuda_version: p.cuda_version}
      }
      sessionStorage.setItem('udr_lastResolved', JSON.stringify(lastResolved))
    }
    // Save last directory
    if (source === 'local' && body.directory_path) saveSetting('lastDir', body.directory_path)
    const pkgCount = result.packages ? result.packages.length : 0
    showToast(`Scan complete: ${pkgCount} packages from ${result.manifests ? result.manifests.length : 0} manifests`, 'success')
  } catch(e) {
    showError(e.message, div)
    showToast(e.message, 'error', 6000)
  }
  hideLoading()
}

document.getElementById('scanBtn').addEventListener('click', () => {
  const dir = document.getElementById('scanPath').value.trim()
  if(!dir) return
  const btn = document.getElementById('scanBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'
  doScan(null, {directory_path: dir}, 'local').then(() => { btn.disabled = false; btn.textContent = 'Scan & Resolve' })
})

document.getElementById('scanGithubBtn').addEventListener('click', () => {
  const url = document.getElementById('scanGithubUrl').value.trim()
  if(!url) return
  const branch = document.getElementById('scanGithubBranch').value
  const btn = document.getElementById('scanGithubBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'
  doScan(null, {repo_url: url, branch}, 'github').then(() => { btn.disabled = false; btn.textContent = 'Scan & Resolve' })
})

document.getElementById('scanUploadBtn').addEventListener('click', () => {
  const fileInput = document.getElementById('scanUploadFile')
  if (!fileInput.files.length) return
  const btn = document.getElementById('scanUploadBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'
  const card = document.getElementById('scanResultCard')
  const div = document.getElementById('scanResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Uploading and resolving...</div>'
  showLoading('Uploading and scanning...', fileInput.files[0].name)
  const formData = new FormData()
  formData.append('file', fileInput.files[0])
  const exportFmt = document.getElementById('scanExportFmt').value
  let url = '/api/v1/scan/upload'
  if (exportFmt) url += `?export=${encodeURIComponent(exportFmt)}`
  fetch(BASE + url, {method:'POST', body: formData})
    .then(async r => {
      if (!r.ok) { let d = r.statusText; try { const j = await r.json(); d = j.detail || d } catch(e) {}; throw new Error(d) }
      return r.json()
    })
    .then(result => {
      lastScanData = result
      div.innerHTML = formatScanResult(result)
      document.getElementById('scanRaw').textContent = JSON.stringify(result, null, 2)
      if (result.export) {
        document.getElementById('scanResultExport').style.display = 'block'
        document.getElementById('scanExportContent').textContent = result.export
      }
      if (result.packages && result.packages.length) {
        document.getElementById('scanLockRow').style.display = 'flex'
        document.getElementById('scanLockMsg').textContent = `${result.packages.length} packages resolved`
        lastResolved = {resolved_packages: {}}
        for (const p of result.packages) {
          lastResolved.resolved_packages[p.name] = {version: p.resolved_version, ecosystem: p.ecosystem, cuda_variant: p.cuda_variant, cuda_version: p.cuda_version}
        }
        sessionStorage.setItem('udr_lastResolved', JSON.stringify(lastResolved))
      }
      showToast(`Scan complete: ${result.packages ? result.packages.length : 0} packages`, 'success')
    })
    .catch(e => { showError(e.message, div); showToast(e.message, 'error', 6000) })
    .finally(() => { btn.disabled = false; btn.textContent = 'Scan & Resolve'; hideLoading() })
})

// --- Graph ---
document.getElementById('graphBtn').addEventListener('click', async () => {
  await withErrorBoundary('graph', async () => {
    const raw = document.getElementById('graphPkgInput').value.trim()
    if(!raw) return
    const eco = document.getElementById('graphEcoSelect').value
    const packages = raw.split(/\s+/)
    const btn = document.getElementById('graphBtn')
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Building tree...'
    const card = document.getElementById('graphResultCard')
    const div = document.getElementById('graphResult')
    card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Resolving dependencies...</div>'
    showLoading('Building dependency graph...')
    try {
      const result = await api('POST', '/api/v1/graph', {packages, ecosystem: eco}, LONG_API_TIMEOUT)
      const trees = result.trees || []
      div.innerHTML = formatGraphTree(trees)
      document.getElementById('graphRaw').textContent = JSON.stringify(result, null, 2)
      showToast(`Graph built: ${trees.length} root packages`, 'success')
    } catch(e) {
      showError(e.message, div)
      showToast(e.message, 'error', 6000)
    }
    btn.disabled = false; btn.textContent = 'Show Tree'
    hideLoading()
  })
})

// --- Verify ---
document.getElementById('verifyLoadBtn').addEventListener('click', () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async e => {
    const text = await e.target.files[0].text()
    document.getElementById('verifyInput').value = text
  }
  input.click()
})

document.getElementById('verifyBtn').addEventListener('click', async () => {
  const text = document.getElementById('verifyInput').value.trim()
  if(!text) return
  let lockData
  try { lockData = JSON.parse(text) } catch(e) { showError('Invalid JSON: ' + e.message, document.getElementById('verifyResult')); return }
  const btn = document.getElementById('verifyBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Verifying...'
  const card = document.getElementById('verifyResultCard')
  const div = document.getElementById('verifyResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Checking all versions...</div>'
  try {
    const result = await api('POST', '/api/v1/verify', {lock_data: lockData}, LONG_API_TIMEOUT)
    div.innerHTML = formatVerifyResult(result)
    document.getElementById('verifyRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Verify'
})

// --- Update ---
document.getElementById('updateBtn').addEventListener('click', async () => {
  const lockText = document.getElementById('updateLockInput').value.trim()
  const pkg = document.getElementById('updatePkgInput').value.trim()
  if(!lockText || !pkg) return
  let lockData
  try { lockData = JSON.parse(lockText) } catch(e) { showError('Invalid JSON: ' + e.message, document.getElementById('updateResult')); return }
  const btn = document.getElementById('updateBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Updating...'
  const card = document.getElementById('updateResultCard')
  const div = document.getElementById('updateResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Re-resolving package...</div>'
  try {
    const result = await api('POST', '/api/v1/update', {lock_data: lockData, package: pkg}, LONG_API_TIMEOUT)
    div.innerHTML = formatUpdateResult(result)
    document.getElementById('updateRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Update'
})

function cacheLastLock(lockData) {
  try { sessionStorage.setItem('udr_lastLock', JSON.stringify(lockData)) } catch(e) {}
}

// --- Generate Lock from Scan ---
document.getElementById('scanLockBtn').addEventListener('click', async () => {
  if (!lastScanData) return
  const btn = document.getElementById('scanLockBtn')
  const msg = document.getElementById('scanLockMsg')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...'
  try {
    const result = await api('POST', '/api/v1/generate-lock', {
      packages: lastScanData.packages || [],
      manifests: lastScanData.manifests || [],
      system: lastScanData.system || {},
      resolution: lastScanData.resolution || {},
    }, LONG_API_TIMEOUT)
    const lockData = result.lock_data
    cacheLastLock(lockData)
    const text = JSON.stringify(lockData, null, 2)
    const blob = new Blob([text], {type:'application/json'})
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = 'udr.lock'
    a.click()
    URL.revokeObjectURL(a.href)
    msg.textContent = 'udr.lock downloaded'
  } catch(e) {
    showError(e.message, msg)
  }
  btn.disabled = false; btn.textContent = '🔒 Generate Lock File'
})

// --- Manifest Lock from Text ---
document.getElementById('manifestLockBtn').addEventListener('click', async () => {
  const raw = document.getElementById('manifestTextInput').value.trim()
  if(!raw) return
  const btn = document.getElementById('manifestLockBtn')
  const card = document.getElementById('scanResultCard')
  const div = document.getElementById('scanResult')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...'
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Processing manifests and resolving...</div>'
  try {
    const manifest_contents = {}
    let currentFile = null
    let currentLines = []
    for (const line of raw.split('\n')) {
      const trimmed = line.trimEnd()
      if (trimmed === '---') {
        if (currentFile) manifest_contents[currentFile] = currentLines.join('\n')
        currentFile = null; currentLines = []
        continue
      }
      if (!currentFile) {
        const pipeIdx = trimmed.indexOf('|')
        if (pipeIdx > 0) {
          currentFile = trimmed.substring(0, pipeIdx).trim()
          const rest = trimmed.substring(pipeIdx + 1)
          if (rest) currentLines.push(rest)
        }
      } else {
        currentLines.push(trimmed)
      }
    }
    if (currentFile) manifest_contents[currentFile] = currentLines.join('\n')
    if (!Object.keys(manifest_contents).length) {
      div.innerHTML = '<div class="alert error">No valid manifest entries. Use format: filename|content</div>'
      btn.disabled = false; btn.textContent = 'Generate Lock from Text'; return
    }
    const systemOverride = document.getElementById('manifestLockSystemSelect').value
    const body = {manifest_contents}
    if (systemOverride === 'cuda12.1') body.system = {gpu: {available: true, cuda: '12.1', devices: [{name: 'Auto'}]}}
    else if (systemOverride === 'cuda11.8') body.system = {gpu: {available: true, cuda: '11.8', devices: [{name: 'Auto'}]}}
    else if (systemOverride === 'cpu') body.system = {gpu: {available: false, cuda: ''}}
    const result = await api('POST', '/api/v1/generate-lock', body, LONG_API_TIMEOUT)
    const lockData = result.lock_data
    cacheLastLock(lockData)
    const lockDiv = document.getElementById('scanResult')
    const pkgCount = Object.keys(lockData.packages||{}).length
    lockDiv.innerHTML = `<div class="alert success">Lock generated: <strong>${pkgCount}</strong> packages resolved</div>` + formatResolveTable({resolved_packages: Object.fromEntries(Object.entries(lockData.packages||{}).map(([k,v]) => [k,{version: v.resolved_version, ecosystem: v.ecosystem, cuda_version: v.cuda_version}]))})
    const text = JSON.stringify(lockData, null, 2)
    const blob = new Blob([text], {type:'application/json'})
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob); a.download = 'udr.lock'; a.click()
    URL.revokeObjectURL(a.href)
    document.getElementById('scanRaw').textContent = JSON.stringify(result, null, 2)
    document.getElementById('scanResultExport').style.display = 'none'
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Generate Lock from Text'
})

// --- Install ---
document.getElementById('installLoadBtn').addEventListener('click', () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async e => {
    const text = await e.target.files[0].text()
    document.getElementById('installInput').value = text
  }
  input.click()
})

document.getElementById('installGenBtn').addEventListener('click', async () => {
  const text = document.getElementById('installInput').value.trim()
  if(!text) return
  let lockData
  try { lockData = JSON.parse(text) } catch(e) { showError('Invalid JSON: ' + e.message, document.getElementById('installResult')); return }
  const btn = document.getElementById('installGenBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...'
  const card = document.getElementById('installResultCard')
  const div = document.getElementById('installResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Generating install commands...</div>'
  try {
    const result = await api('POST', '/api/v1/install-commands', {lock_data: lockData})
    div.innerHTML = formatInstallCommands(result)
    document.getElementById('installRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Generate Commands'
})

// --- Restore ---
document.getElementById('restoreLoadBtn').addEventListener('click', () => {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.json'
  input.onchange = async e => {
    const text = await e.target.files[0].text()
    document.getElementById('restoreInput').value = text
  }
  input.click()
})

document.getElementById('restoreGenBtn').addEventListener('click', async () => {
  const text = document.getElementById('restoreInput').value.trim()
  if(!text) return
  let lockData
  try { lockData = JSON.parse(text) } catch(e) { showError('Invalid JSON: ' + e.message, document.getElementById('restoreResult')); return }
  const btn = document.getElementById('restoreGenBtn')
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...'
  const card = document.getElementById('restoreResultCard')
  const div = document.getElementById('restoreResult')
  card.style.display = 'block'; div.innerHTML = '<div class="loading-state"><span class="spinner"></span>Generating restore commands...</div>'
  try {
    const result = await api('POST', '/api/v1/restore-commands', {lock_data: lockData})
    div.innerHTML = formatInstallCommands(result)
    document.getElementById('restoreRaw').textContent = JSON.stringify(result, null, 2)
  } catch(e) {
    showError(e.message, div)
  }
  btn.disabled = false; btn.textContent = 'Generate Commands'
})

function formatInstallCommands(result) {
  const cmds = result.commands || []
  if (!cmds.length) return '<div class="alert warning">No install commands generated</div>'
  let h = `<div class="alert success">Generated commands for <strong>${result.total_packages}</strong> packages across <strong>${cmds.length}</strong> ecosystems</div>`
  for (const c of cmds) {
    h += `<div class="card" style="margin-top:8px;padding:12px 16px;background:var(--bg-elevated)">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
        <span class="badge accent">${c.ecosystem}</span>
        <span style="font-size:11px;color:var(--text-dim)">${c.package_count} packages</span>
        <button class="ghost" onclick="copyToClipboard(this, '${c.command.replace(/`/g,'\\`').replace(/'/g,"\\'").replace(/\n/g,'\\n')}')" style="margin-left:auto">Copy</button>
      </div>
      <pre style="font-size:12px;padding:8px 12px;margin:0;max-height:none;background:var(--bg-body);border-radius:var(--radius-sm);white-space:pre-wrap">${c.command}</pre>
    </div>`
  }
  return h
}

function copyToClipboard(btn, text) {
  navigator.clipboard.writeText(text).then(() => {
    btn.textContent = 'Copied!'
    setTimeout(() => { btn.textContent = 'Copy' }, 2000)
  })
}

// Enter key handlers
document.getElementById('searchInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('searchBtn').click() })
document.getElementById('pkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('resolveBtn').click() })
document.getElementById('detPkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('detBtn').click() })
document.getElementById('verPkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('verBtn').click() })
document.getElementById('depPkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('depBtn').click() })
document.getElementById('comPkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('comBtn').click() })
document.getElementById('graphPkgInput').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('graphBtn').click() })
document.getElementById('scanGithubUrl').addEventListener('keydown', e => { if (e.key === 'Enter') document.getElementById('scanGithubBtn').click() })

init()
