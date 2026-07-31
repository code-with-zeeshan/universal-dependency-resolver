/* mermaid-fix.js
 *
 * Workaround for Material for MkDocs mermaid rendering: mermaid bakes an
 * inline `style="color:#fff !important"` onto subgraph/cluster title spans
 * (<span class="nodeLabel"> inside g.cluster-label). That inline style is
 * inserted into a closed shadow root, so no stylesheet rule (even one with
 * `!important`) can override it, and in the "default" (light) color scheme
 * the white-on-white titles are invisible.
 *
 * The Material bundle lazily injects the mermaid <script> tag, which assigns
 * `globalThis["mermaid"]`. We install an accessor property on `window.mermaid`
 * that wraps `mermaid.render` at assignment time (which runs before the
 * bundle's script "load" handler invokes render), rewriting the returned SVG
 * string so cluster titles follow the active color scheme.
 */
(function () {
  "use strict";

  var realMermaid;

  function fixSvg(svg) {
    return svg.replace(
      /style="color:#fff !important"/g,
      'style="color:var(--md-mermaid-label-fg-color) !important"'
    );
  }

  function wrap(inst) {
    if (!inst || typeof inst.render !== "function" || inst.__udrWrapped) return;
    var origRender = inst.render;
    inst.render = function (id, text, opts) {
      var result = origRender.call(this, id, text, opts);
      return Promise.resolve(result).then(function (out) {
        if (out && typeof out.svg === "string") {
          out.svg = fixSvg(out.svg);
        }
        return out;
      });
    };
    inst.__udrWrapped = true;
  }

  function installAccessor() {
    try {
      var existing = Object.getOwnPropertyDescriptor(window, "mermaid");
      if (existing && existing.get) {
        if (typeof existing.get() === "object" && existing.get()) wrap(existing.get());
        return;
      }
      Object.defineProperty(window, "mermaid", {
        configurable: true,
        enumerable: true,
        get: function () {
          return realMermaid;
        },
        set: function (value) {
          realMermaid = value;
          wrap(value);
        },
      });
    } catch (error) {
      var timer = setInterval(function () {
        if (typeof window.mermaid !== "undefined" && window.mermaid) {
          clearInterval(timer);
          wrap(window.mermaid);
        }
      }, 100);
    }
  }

  if (typeof window.mermaid !== "undefined" && window.mermaid) {
    wrap(window.mermaid);
  } else {
    installAccessor();
  }
})();
