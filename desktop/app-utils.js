// Pure formatting helpers for UDR desktop app (no DOM dependency)
// Used by app.js in Electron renderer and tested directly in Node.js

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
    h += '<div style="margin-top:8px;font-size:12px;color:var(--yellow)">' + resolved.warnings.map(w => '\u26A0 ' + w).join('<br>') + '</div>'
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
  if (issues.length) h += ` &mdash; ${issues.length} issue(s) found`
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
    return `<div class="alert success"><strong>${data.package}</strong> updated: ${data.old_version} &rarr; ${data.new_version}</div>`
  } else {
    return `<div class="alert success">${data.package} is already at ${data.new_version} &mdash; no update needed</div>`
  }
}

function cacheLastLock(lockData) {
  try { sessionStorage.setItem('udr_lastLock', JSON.stringify(lockData)) } catch(e) {}
}

// Support both browser (global) and Node.js (module.exports)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
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
  }
}
