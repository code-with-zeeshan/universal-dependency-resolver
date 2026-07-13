const Utils = {
  escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },

  plural(n, s) { return n === 1 ? s : s + 's'; },

  formatDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleString();
    } catch { return iso; }
  },

  timeAgo(iso) {
    if (!iso) return '—';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    return `${days}d ago`;
  },

  truncate(str, n = 60) {
    return str && str.length > n ? str.slice(0, n) + '…' : str;
  },

  severityClass(sev) {
    const s = (sev || '').toLowerCase();
    if (s.includes('critical')) return 'critical';
    if (s.includes('high')) return 'high';
    if (s.includes('moderate') || s.includes('medium')) return 'moderate';
    if (s.includes('low')) return 'low';
    if (s === 'error') return 'error';
    if (s === 'warning') return 'warning';
    if (s === 'ok' || s === 'pass') return 'ok';
    return 'low';
  },

  severityBadge(sev) {
    const cls = this.severityClass(sev);
    return `<span class="severity ${cls}">${this.escapeHtml(sev)}</span>`;
  },

  ecoColor(eco) {
    const colors = {
      pypi: '#3775a9', npm: '#cb3837', conda: '#44a833', maven: '#c71a36',
      crates: '#f7df1e', gomodules: '#00add8', nuget: '#004880', rubygems: '#e9573f',
      packagist: '#4f5b93', cocoapods: '#e95420', homebrew: '#fbb040', apt: '#e44d42',
      apk: '#0d597f', dart: '#0175c2', pub: '#0175c2', gradle: '#02303a',
      swift: '#f05138', hex: '#6e4a7e', haskell: '#5e5184', nixos: '#5277c3',
      guix: '#e38b29',
    };
    return colors[eco] || 'var(--text-muted)';
  },

  ecoBadge(eco) {
    const color = this.ecoColor(eco);
    return `<span class="eco-badge" style="color:${color};border-color:${color}40">${this.escapeHtml(eco)}</span>`;
  },

  parseLockFile(text) {
    try {
      return JSON.parse(text);
    } catch {
      throw new Error('Invalid JSON in lock file');
    }
  },

  getPackagesFromLock(lockData) {
    return lockData?.packages || lockData?.resolved_packages || {};
  },

  getPackageCount(lockData) {
    return Object.keys(this.getPackagesFromLock(lockData)).length;
  },

  makeToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    const icons = { success: '\u2713', error: '\u2717', info: '\u2139' };
    el.innerHTML = `<span>${icons[type] || ''}</span> ${this.escapeHtml(message)}`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 4000);
  },

  async readFileAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = e => resolve(e.target.result);
      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsText(file);
    });
  },

  downloadFile(content, filename, mimeType = 'application/json') {
    const blob = new Blob([typeof content === 'string' ? content : JSON.stringify(content, null, 2)], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },

  generateSBOM(lockData, format = 'spdx') {
    const packages = this.getPackagesFromLock(lockData);
    const docName = lockData?.metadata?.project_name || 'universal-dependency-project';
    const created = new Date().toISOString();

    if (format === 'spdx') {
      const spdx = {
        spdxVersion: 'SPDX-2.3',
        dataLicense: 'CC0-1.0',
        SPDXID: 'SPDXRef-DOCUMENT',
        name: docName,
        documentNamespace: `https://spdx.org/spdxdocs/${docName}-${created.replace(/[:.]/g, '-')}`,
        creationInfo: { creators: ['Tool: universal-dependency-resolver-frontend'], created },
        packages: Object.entries(packages).map(([name, info]) => ({
          name,
          SPDXID: `SPDXRef-${name.replace(/[^a-zA-Z0-9]/g, '-')}`,
          versionInfo: info.resolved_version || info.version || '',
          supplier: `NOASSERTION`,
          downloadLocation: 'NOASSERTION',
          licenseConcluded: info.license || 'NOASSERTION',
          licenseDeclared: info.license || 'NOASSERTION',
          copyrightText: 'NOASSERTION',
          externalRefs: [{
            referenceCategory: 'PACKAGE-MANAGER',
            referenceType: 'purl',
            referenceLocator: `pkg:${info.ecosystem || 'generic'}/${name}@${info.resolved_version || info.version || ''}`,
          }],
        })),
        relationships: [],
      };
      Object.entries(packages).forEach(([name, info]) => {
        const deps = info.dependencies || {};
        Object.values(deps).flat().forEach(dep => {
          Object.keys(dep).forEach(depName => {
            spdx.relationships.push({
              spdxElementId: `SPDXRef-${name.replace(/[^a-zA-Z0-9]/g, '-')}`,
              relationshipType: 'DEPENDS_ON',
              relatedSpdxElement: `SPDXRef-${depName.replace(/[^a-zA-Z0-9]/g, '-')}`,
            });
          });
        });
      });
      return JSON.stringify(spdx, null, 2);
    }

    if (format === 'cyclonedx') {
      const cd = {
        bomFormat: 'CycloneDX',
        specVersion: '1.5',
        version: 1,
        metadata: { timestamp: created, tools: [{ name: 'universal-dependency-resolver-frontend' }] },
        components: Object.entries(packages).map(([name, info]) => ({
          type: 'library',
          name,
          version: info.resolved_version || info.version || '',
          purl: `pkg:${info.ecosystem || 'generic'}/${name}@${info.resolved_version || info.version || ''}`,
          licenses: info.license ? [{ license: { name: info.license } }] : [],
        })),
        dependencies: [],
      };
      Object.entries(packages).forEach(([name, info]) => {
        const refs = [];
        const deps = info.dependencies || {};
        Object.values(deps).flat().forEach(dep => {
          Object.keys(dep).forEach(dn => refs.push({ ref: `pkg:${info.ecosystem || 'generic'}/${dn}@${dep[dn] || ''}` }));
        });
        cd.dependencies.push({ ref: `pkg:${info.ecosystem || 'generic'}/${name}@${info.resolved_version || ''}`, dependsOn: refs.map(r => r.ref) });
      });
      return JSON.stringify(cd, null, 2);
    }
    throw new Error(`Unknown SBOM format: ${format}`);
  },

  async checkVulnerabilitiesOSV(packages) {
    const results = [];
    for (const [name, info] of Object.entries(packages)) {
      const eco = info.ecosystem || 'PyPI';
      const ecoMap = { pypi: 'PyPI', npm: 'npm', crates: 'crates.io', rubygems: 'RubyGems', nuget: 'NuGet',
        packagist: 'Packagist', maven: 'Maven', gomodules: 'Go', cargo: 'crates.io',
        conda: 'conda', pub: 'Pub', cocoapods: 'CocoaPods', homebrew: 'Homebrew',
        gradle: 'Maven', swift: 'Swift', hex: 'Hex', haskell: 'Hackage',
        apt: 'Debian', apk: 'Alpine' };
      const osvEco = ecoMap[eco] || eco;
      const ver = info.resolved_version || info.version;
      if (!ver) continue;

      try {
        const res = await fetch('https://api.osv.dev/v1/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ package: { name, ecosystem: osvEco }, version: ver }),
          signal: AbortSignal.timeout(10000),
        });
        if (!res.ok) continue;
        const data = await res.json();
        if (data.vulns) {
          data.vulns.forEach(v => {
            const aliases = v.aliases || [];
            results.push({
              package: name,
              ecosystem: eco,
              version: ver,
              id: v.id || aliases[0] || 'UNKNOWN',
              severity: (v.severity || []).find(s => s.type === 'CVSS_V3')?.score > 7 ? 'HIGH'
                : (v.severity || []).find(s => s.type === 'CVSS_V3')?.score > 4 ? 'MODERATE' : 'LOW',
              summary: v.summary || v.details?.substring(0, 120) || 'No description',
              fixedVersion: (v.affected?.[0]?.ranges?.[0]?.events?.find(e => e.fixed)?.fixed) || null,
              aliases,
            });
          });
        }
      } catch {}
    }
    return results;
  },

  checkLicenses(packages) {
    const results = [];
    const spdxCompat = {
      'MIT': true, 'Apache-2.0': true, 'BSD-2-Clause': true, 'BSD-3-Clause': true,
      'ISC': true, 'Unlicense': true, 'CC0-1.0': true, '0BSD': true,
      'LGPL-2.1-only': 'copyleft', 'LGPL-2.1-or-later': 'copyleft',
      'LGPL-3.0-only': 'copyleft', 'LGPL-3.0-or-later': 'copyleft',
      'GPL-2.0-only': 'copyleft', 'GPL-2.0-or-later': 'copyleft',
      'GPL-3.0-only': 'copyleft', 'GPL-3.0-or-later': 'copyleft',
      'MPL-2.0': 'weak-copyleft', 'EPL-2.0': 'weak-copyleft',
      'AGPL-3.0-only': 'strong-copyleft', 'AGPL-3.0-or-later': 'strong-copyleft',
    };
    for (const [name, info] of Object.entries(packages)) {
      const lic = info.license || 'Unknown';
      const compat = spdxCompat[lic];
      results.push({
        package: name,
        ecosystem: info.ecosystem || '?',
        version: info.resolved_version || info.version || '?',
        license: lic,
        status: compat === true ? 'approved' : compat ? 'restricted' : 'unknown',
      });
    }
    return results;
  },

  checkPolicy(packages, policyYaml, vulns = [], licenses = []) {
    const violations = [];
    const policy = this._parsePolicyYaml(policyYaml);

    if (policy['no-deprecated']) {
      Object.entries(packages).forEach(([name, info]) => {
        if (info.deprecated) violations.push({ package: name, rule: 'no-deprecated', message: 'Package is deprecated', severity: 'error' });
      });
    }

    if (policy['no-yanked']) {
      Object.entries(packages).forEach(([name, info]) => {
        if (info.yanked) violations.push({ package: name, rule: 'no-yanked', message: 'Package version is yanked', severity: 'error' });
      });
    }

    if (policy['no-gpl']) {
      licenses.forEach(l => {
        if ((l.license || '').startsWith('GPL')) violations.push({ package: l.package, rule: 'no-gpl', message: `GPL license: ${l.license}`, severity: 'error' });
      });
    }

    if (policy['no-agpl']) {
      licenses.forEach(l => {
        if ((l.license || '').startsWith('AGPL')) violations.push({ package: l.package, rule: 'no-agpl', message: `AGPL license: ${l.license}`, severity: 'error' });
      });
    }

    if (typeof policy['max-vulnerabilities'] === 'number') {
      const vulnCount = vulns.length;
      if (vulnCount > policy['max-vulnerabilities']) {
        violations.push({ package: '*', rule: 'max-vulnerabilities', message: `Found ${vulnCount} vulns, max is ${policy['max-vulnerabilities']}`, severity: 'error' });
      }
    }

    if (typeof policy['max-critical-vulns'] === 'number') {
      const critical = vulns.filter(v => v.severity === 'CRITICAL' || v.severity === 'HIGH').length;
      if (critical > policy['max-critical-vulns']) {
        violations.push({ package: '*', rule: 'max-critical-vulns', message: `Found ${critical} critical/high vulns, max is ${policy['max-critical-vulns']}`, severity: 'error' });
      }
    }

    if (policy['allowed-licenses'] && Array.isArray(policy['allowed-licenses'])) {
      licenses.forEach(l => {
        if (!policy['allowed-licenses'].includes(l.license)) {
          violations.push({ package: l.package, rule: 'allowed-licenses', message: `License not allowed: ${l.license}`, severity: 'warning' });
        }
      });
    }

    if (policy['blocked-packages'] && Array.isArray(policy['blocked-packages'])) {
      policy['blocked-packages'].forEach(bp => {
        Object.keys(packages).forEach(name => {
          if (name === bp || name.match(new RegExp(bp))) {
            violations.push({ package: name, rule: 'blocked-packages', message: `Package is blocked by policy`, severity: 'error' });
          }
        });
      });
    }

    return violations;
  },

  _parsePolicyYaml(yaml) {
    const result = {};
    const lines = yaml.split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#') || trimmed.startsWith('---')) continue;
      const colonIdx = trimmed.indexOf(':');
      if (colonIdx === -1) continue;
      const key = trimmed.slice(0, colonIdx).trim();
      let val = trimmed.slice(colonIdx + 1).trim();
      if (val === 'true') result[key] = true;
      else if (val === 'false') result[key] = false;
      else if (/^\d+$/.test(val)) result[key] = parseInt(val, 10);
      else if (val.startsWith('[') && val.endsWith(']')) {
        result[key] = val.slice(1, -1).split(',').map(s => s.trim().replace(/['"]/g, '')).filter(Boolean);
      } else if (val.startsWith('- ')) {
        if (!result[key]) result[key] = [];
        result[key].push(val.slice(2).trim().replace(/['"]/g, ''));
      } else if (val) {
        result[key] = val.replace(/['"]/g, '');
      }
    }
    return result;
  },

  makeSpinner() {
    const div = document.createElement('div');
    div.className = 'loading-overlay';
    div.innerHTML = '<div class="spinner spinner-lg"></div><span>Loading...</span>';
    return div;
  },

  treeToGraphData(trees) {
    const nodes = new Map();
    const links = [];
    const seenEdges = new Set();
    const addNode = (name, info) => {
      if (!nodes.has(name)) {
        nodes.set(name, { id: name, ...info, children: [] });
      }
      return nodes.get(name);
    };
    const traverse = (node, parentId) => {
      if (!node || !node.name) return;
      const n = addNode(node.name, { version: node.version || '', ecosystem: node.ecosystem || '' });
      if (parentId) {
        const edgeKey = `${parentId}->${node.name}`;
        if (!seenEdges.has(edgeKey)) {
          seenEdges.add(edgeKey);
          links.push({ source: parentId, target: node.name });
        }
      }
      (node.children || []).forEach(c => traverse(c, node.name));
    };
    (trees || []).forEach(t => traverse(t, null));
    return { nodes: Array.from(nodes.values()), links };
  },

  drawForceGraph(svgElement, tooltipEl, nodeCountEl, data) {
    svgElement.innerHTML = '';
    if (!data || !data.nodes.length) return;

    const width = svgElement.clientWidth || 900;
    const height = 600;
    nodeCountEl.textContent = `${data.nodes.length} nodes, ${data.links.length} edges`;

    const svg = d3.select(svgElement);
    const g = svg.append('g');

    const zoom = d3.zoom().scaleExtent([0.1, 4]).on('zoom', (event) => {
      g.attr('transform', event.transform);
    });
    svg.call(zoom);

    const ecoColors = {
      pypi: '#3775a9', npm: '#cb3837', conda: '#44a833', maven: '#c71a36', crates: '#f7df1e',
      gomodules: '#00add8', nuget: '#004880', rubygems: '#e9573f', packagist: '#4f5b93',
      cocoapods: '#e95420', homebrew: '#fbb040', apt: '#e44d42', apk: '#0d597f',
      helm: '#0f1689', terraform: '#7b42bc', vcpkg: '#00a4ef', conan: '#0088cc',
      docker: '#0db7ed', nixos: '#5277c3', guix: '#e38b29',
    };

    const simulation = d3.forceSimulation(data.nodes)
      .force('link', d3.forceLink(data.links).id(d => d.id).distance(120))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40));

    const link = g.append('g')
      .selectAll('line')
      .data(data.links)
      .join('line')
      .attr('stroke', 'var(--border)')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6);

    const node = g.append('g')
      .selectAll('g')
      .data(data.nodes)
      .join('g')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        })
      );

    node.append('circle')
      .attr('r', 8)
      .attr('fill', d => ecoColors[d.ecosystem] || '#888')
      .attr('stroke', '#fff')
      .attr('stroke-width', 1.5)
      .attr('cursor', 'pointer');

    node.append('text')
      .text(d => d.id)
      .attr('x', 12)
      .attr('y', 4)
      .attr('font-size', '0.75rem')
      .attr('fill', 'var(--text-primary)')
      .attr('pointer-events', 'none');

    node.on('mouseover', (event, d) => {
      tooltipEl.style.display = 'block';
      tooltipEl.innerHTML = `<strong>${d.id}</strong><br>Version: ${d.version || 'latest'}<br>Ecosystem: ${d.ecosystem || 'unknown'}`;
    }).on('mousemove', (event) => {
      tooltipEl.style.left = (event.offsetX + 10) + 'px';
      tooltipEl.style.top = (event.offsetY + 10) + 'px';
    }).on('mouseout', () => {
      tooltipEl.style.display = 'none';
    });

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    document.getElementById('graph-zoom-in')?.addEventListener('click', () => {
      svg.transition().duration(300).call(zoom.scaleBy, 1.3);
    });
    document.getElementById('graph-zoom-out')?.addEventListener('click', () => {
      svg.transition().duration(300).call(zoom.scaleBy, 0.7);
    });
    document.getElementById('graph-reset')?.addEventListener('click', () => {
      svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);
    });

    svg.on('dblclick.zoom', null);
  },
};
