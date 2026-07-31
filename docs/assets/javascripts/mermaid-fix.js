/* mermaid-fix.js
 *
 * Enhancements for Material for MkDocs mermaid rendering:
 *
 * 1. Cluster/subgraph title contrast. mermaid bakes an inline
 *    `style="color:#fff !important"` onto subgraph title spans (<span
 *    class="nodeLabel"> inside g.cluster-label), which sits inside a closed
 *    shadow root where no stylesheet rule can override it. The correct color
 *    depends on the cluster's own background:
 *      - explicit dark fill (style "fill:#XXXXXX" on the cluster rect) -> the
 *        author intends a dark badge, so the title must stay WHITE;
 *      - no explicit fill (theme background) -> the title must follow the
 *        active color scheme via --md-mermaid-label-fg-color.
 *    We compute the relative luminance of each cluster rect's fill and pick
 *    the label color accordingly, so titles are readable in BOTH the light
 *    and dark (slate) color schemes.
 *
 * 2. Click-to-enlarge. Clicking any mermaid diagram opens it in a lightbox
 *    overlay at a larger size (GitHub-style), so details are visible on
 *    small screens. Close by clicking the backdrop, the "x", or Esc.
 *
 * The Material bundle lazily injects the mermaid <script> tag, which assigns
 * `globalThis["mermaid"]`. We install an accessor property on `window.mermaid`
 * that wraps `mermaid.render` at assignment time (which runs before the
 * bundle's script "load" handler invokes render), rewriting the returned SVG
 * string before it is inserted into the shadow root. We also wrap
 * `Element.prototype.attachShadow` so we can locate rendered diagrams for the
 * lightbox.
 */
(function () {
  "use strict";

  var realMermaid;

  /* ---------- color helpers ---------- */

  function parseColor(str) {
    if (!str) return null;
    str = str.trim();
    var m = str.match(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/);
    if (m) {
      var hex = m[1];
      if (hex.length === 3) {
        hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
      }
      var n = parseInt(hex, 16);
      return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
    }
    m = str.match(/rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)/);
    if (m) {
      return { r: +m[1], g: +m[2], b: +m[3] };
    }
    return null;
  }

  function luminance(c) {
    function lin(v) {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    }
    return 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  }

  /* ---------- SVG post-processing ---------- */

  var FILL_RE = /(fill:\s*)(#[0-9a-fA-F]{3,6}|rgba?\([^)]*\))/;

  function fixSvg(svg) {
    var result = svg;
    var open = result.indexOf('<g class="cluster"');
    while (open !== -1) {
      var end = result.indexOf('</g>', open);
      if (end === -1) break;
      var block = result.slice(open, end);
      var rectStart = block.indexOf("<rect");
      if (rectStart !== -1) {
        var rectEnd = block.indexOf(">", rectStart);
        var rectTag = block.slice(rectStart, rectEnd);
        var fillMatch = FILL_RE.exec(rectTag);
        var labelStart = block.indexOf('<span class="nodeLabel"');
        var color = null;
        if (labelStart !== -1) {
          var labelEnd = block.indexOf(">", labelStart);
          var labelTag = block.slice(labelStart, labelEnd);
          var labelStyle = labelTag.match(/style="([^"]*)"/);
          if (labelStyle) {
            if (fillMatch) {
              var col = parseColor(fillMatch[2]);
              color = col && luminance(col) < 0.4
                ? "#fff"
                : "var(--md-mermaid-label-fg-color)";
            } else {
              color = "var(--md-mermaid-label-fg-color)";
            }
            var newTag = labelTag.replace(
              /style="[^"]*"/,
              function (m, s) {
                return m.replace(/(color:\s*)[^;"]*/, "$1" + color);
              }
            );
            result = result.slice(0, open + labelStart) +
              newTag +
              result.slice(open + labelEnd);
          }
        }
      }
      open = result.indexOf('<g class="cluster"', open + 1);
    }
    return result;
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

  /* ---------- mermaid global accessor ---------- */

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

  /* ---------- click-to-enlarge lightbox ---------- */

  var diagramShadows = new WeakMap();

  function wrapAttachShadow() {
    try {
      var proto = Element.prototype;
      var origAttach = proto.attachShadow;
      if (origAttach.__udrWrapped) return;
      proto.attachShadow = function (init) {
        var shadow = origAttach.call(this, init);
        try {
          if (this.classList && this.classList.contains("mermaid") && shadow) {
            diagramShadows.set(this, shadow);
          }
        } catch (error) {
          /* ignore */
        }
        return shadow;
      };
      proto.attachShadow.__udrWrapped = true;
    } catch (error) {
      /* ignore */
    }
  }
  wrapAttachShadow();

  var lightbox = null;

  function closeLightbox() {
    if (!lightbox) return;
    document.removeEventListener("keydown", lightboxKeydown);
    if (lightbox.parentNode) lightbox.parentNode.removeChild(lightbox);
    lightbox = null;
  }

  function lightboxKeydown(e) {
    if (e.key === "Escape") closeLightbox();
  }

  function openLightbox(host) {
    var shadow = diagramShadows.get(host);
    if (!shadow) return;
    var src = shadow.querySelector("svg");
    if (!src) return;
    var clone = src.cloneNode(true);
    clone.setAttribute("width", "auto");
    clone.setAttribute("height", "auto");
    clone.style.width = "auto";
    clone.style.height = "auto";
    clone.style.maxWidth = "100%";
    clone.style.maxHeight = "100%";

    var overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.style.cssText =
      "position:fixed;top:0;left:0;right:0;bottom:0;z-index:2147483000;" +
      "background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center;padding:16px;";

    var panel = document.createElement("div");
    panel.style.cssText =
      "position:relative;max-width:94vw;max-height:92vh;overflow:auto;" +
      "background:var(--md-default-bg-color,#fff);border-radius:8px;" +
      "box-shadow:0 12px 48px rgba(0,0,0,0.35);padding:24px;";

    var closeBtn = document.createElement("button");
    closeBtn.textContent = "\u00d7";
    closeBtn.setAttribute("aria-label", "Close diagram");
    closeBtn.style.cssText =
      "position:absolute;top:8px;right:8px;width:32px;height:32px;line-height:28px;" +
      "border:0;border-radius:50%;cursor:pointer;font-size:20px;color:#fff;" +
      "background:rgba(0,0,0,0.5);z-index:2;";

    panel.appendChild(clone);
    panel.appendChild(closeBtn);
    overlay.appendChild(panel);
    document.body.appendChild(overlay);
    lightbox = overlay;

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay || e.target === closeBtn) closeLightbox();
    });
    document.addEventListener("keydown", lightboxKeydown);
  }

  document.addEventListener("click", function (e) {
    var path = e.composedPath ? e.composedPath() : [];
    for (var i = 0; i < path.length; i++) {
      var node = path[i];
      if (node && node.nodeType === 1 && diagramShadows.has(node)) {
        openLightbox(node);
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    }
  }, true);
})();
