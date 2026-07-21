const fs = require('fs');
const path = require('path');

const utilsCode = fs.readFileSync(path.join(__dirname, 'js/utils.js'), 'utf8');
const patched = utilsCode.replace('const Utils =', 'globalThis.Utils =');
eval(patched);

if (typeof AbortSignal !== 'undefined' && !AbortSignal.timeout) {
  AbortSignal.timeout = function timeout(ms) {
    const ctrl = new AbortController();
    setTimeout(() => ctrl.abort(), ms);
    return ctrl.signal;
  };
}
