/* source-downloads.js
 *
 * Adds a "downloads" fact to the header repo link, styled exactly like
 * Material's own "version / stars / forks" facts (small text + mask icon).
 * The count is fetched from the shields.io JSON endpoint for PyPI monthly
 * downloads. Degrades silently (no fact) if the network fails.
 */
(function () {
  "use strict";

  function formatNumber(value) {
    var m = String(value).match(/^[\d.]+/);
    if (!m) return String(value);
    var n = parseFloat(m[0]);
    if (isNaN(n)) return String(value);
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return String(Math.round(n));
  }

  function addDownloadsFact() {
    var facts = document.querySelector(".md-source__facts");
    if (!facts) return;
    if (facts.querySelector(".md-source__fact--udr-downloads")) return;

    var li = document.createElement("li");
    li.className = "md-source__fact md-source__fact--udr-downloads";
    li.setAttribute("title", "PyPI downloads (last month)");
    li.textContent = "\u00b7\u00b7\u00b7";
    facts.appendChild(li);

    fetch("https://img.shields.io/pypi/dm/ud-resolver.json?_=" + Date.now())
      .then(function (resp) {
        if (!resp.ok) throw new Error("bad status " + resp.status);
        return resp.json();
      })
      .then(function (data) {
        if (data && data.value && data.value.indexOf("rate limited") === -1) {
          li.textContent = formatNumber(data.value) + "/mo";
        } else {
          throw new Error("no value");
        }
      })
      .catch(function (err) {
        // Transient upstream rate-limits: retry once after a short delay.
        if (!li.__retried) {
          li.__retried = true;
          setTimeout(function () {
            fetch("https://img.shields.io/pypi/dm/ud-resolver.json?_=" + Date.now())
              .then(function (resp) { return resp.ok ? resp.json() : null; })
              .then(function (data) {
                if (data && data.value && data.value.indexOf("rate limited") === -1) {
                  li.textContent = formatNumber(data.value) + "/mo";
                } else {
                  if (li.parentNode) li.parentNode.removeChild(li);
                }
              })
              .catch(function () {
                if (li.parentNode) li.parentNode.removeChild(li);
              });
          }, 3000);
        } else {
          if (li.parentNode) li.parentNode.removeChild(li);
        }
      });
  }

  // Material populates .md-source__facts asynchronously (GitHub API). Poll a
  // short while until the facts list exists, then append ours.
  var tries = 0;
  (function poll() {
    var facts = document.querySelector(".md-source__facts");
    if (facts) {
      addDownloadsFact();
      return;
    }
    if (++tries < 40) {
      setTimeout(poll, 250);
    }
  })();
})();
