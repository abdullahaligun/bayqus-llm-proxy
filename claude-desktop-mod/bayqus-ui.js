// Bayqus Proxy Claude Desktop UI Entegrasyonu (Renderer / Page Script)
(function () {
  if (window.__BAYQUS_INJECTED__) return;
  window.__BAYQUS_INJECTED__ = true;

  const CSS = `
    #bayqus-route-container {
      position: fixed;
      top: 10px;
      right: 140px;
      z-index: 2147483647;
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 3px 10px;
      border-radius: 9999px;
      background: rgba(24, 24, 27, 0.90);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.15);
      box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      font-size: 12px;
      color: #f4f4f5;
      user-select: none;
      -webkit-app-region: no-drag;
      cursor: default;
      transition: all 0.2s ease;
    }
    #bayqus-route-container:hover {
      border-color: rgba(255, 255, 255, 0.32);
      box-shadow: 0 6px 20px rgba(0, 0, 0, 0.55);
    }
    #bayqus-status-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      transition: background 0.3s ease;
      flex-shrink: 0;
    }
    #bayqus-status-dot.gateway {
      background: #3b82f6;
    }
    .bayqus-label {
      font-weight: 500;
      color: #a1a1aa;
      font-size: 11px;
      letter-spacing: 0.2px;
    }
    #bayqus-route-select {
      background: transparent;
      color: #fafafa;
      border: none;
      outline: none;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      padding-right: 2px;
    }
    #bayqus-route-select option {
      background: #18181b;
      color: #fafafa;
      font-weight: 500;
      padding: 6px 10px;
    }
    #bayqus-toast {
      position: fixed;
      top: 48px;
      right: 140px;
      z-index: 2147483647;
      padding: 6px 14px;
      border-radius: 8px;
      background: rgba(16, 185, 129, 0.95);
      color: #ffffff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 11px;
      font-weight: 500;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
      pointer-events: none;
      opacity: 0;
      transform: translateY(-4px);
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }
    #bayqus-toast.show {
      opacity: 1;
      transform: translateY(0);
    }
  `;

  function injectStyles() {
    if (document.getElementById("bayqus-styles")) return;
    const styleEl = document.createElement("style");
    styleEl.id = "bayqus-styles";
    styleEl.textContent = CSS;
    (document.head || document.documentElement).appendChild(styleEl);
  }

  function getChatId() {
    const url = window.location.href;
    const m = url.match(/\/chat\/([a-zA-Z0-9-]+)/);
    if (m) return m[1];
    if (url.includes("/new")) return "new";
    return "global";
  }

  function showToast(msg, bg) {
    let toast = document.getElementById("bayqus-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "bayqus-toast";
      (document.body || document.documentElement).appendChild(toast);
    }
    toast.textContent = msg;
    toast.style.background = bg || "rgba(16, 185, 129, 0.95)";
    toast.classList.add("show");
    setTimeout(() => {
      toast.classList.remove("show");
    }, 2200);
  }

  function updateDot(route) {
    const dot = document.getElementById("bayqus-status-dot");
    if (!dot) return;
    dot.className = route === "gateway" ? "gateway" : "";
  }

  function createWidget() {
    if (document.getElementById("bayqus-route-container")) return;
    if (!document.body) return;

    injectStyles();

    const el = document.createElement("div");
    el.id = "bayqus-route-container";
    el.title = "Bayqus Proxy Rota Seçici";
    el.innerHTML = `
      <span style="font-size: 13px;">🦉</span>
      <div id="bayqus-status-dot"></div>
      <span class="bayqus-label">Rota:</span>
      <select id="bayqus-route-select" title="Bu sohbet için rota seçin">
        <option value="abonelik">Abonelik</option>
        <option value="gateway">Gateway</option>
      </select>
    `;

    document.body.appendChild(el);

    const sel = document.getElementById("bayqus-route-select");
    sel.addEventListener("change", () => {
      const val = sel.value;
      const cid = getChatId();
      updateDot(val);
      el.title = `Bayqus Rota: ${val.toUpperCase()} (Oturum: ${cid})`;
      console.log("__BAYQUS_PIN__:" + JSON.stringify({ session: cid, route: val }));
      showToast(
        cid === "new" || cid === "global"
          ? `Varsayılan rota: ${val.toUpperCase()}`
          : `Bu sohbet: ${val.toUpperCase()} rotasına sabitlendi`,
        val === "gateway" ? "rgba(59, 130, 246, 0.95)" : "rgba(16, 185, 129, 0.95)"
      );
    });

    const cid = getChatId();
    el.title = `Bayqus Rota (Oturum: ${cid})`;
    console.log("__BAYQUS_QUERY__:" + JSON.stringify({ session: cid }));
  }

  window.__bayqusSetRoute = function (route) {
    const sel = document.getElementById("bayqus-route-select");
    const container = document.getElementById("bayqus-route-container");
    if (sel && route) {
      sel.value = route;
      updateDot(route);
      if (container) {
        container.title = `Bayqus Rota: ${route.toUpperCase()} (Oturum: ${getChatId()})`;
      }
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createWidget);
  } else {
    createWidget();
  }

  // URL değişikliklerini dinle
  let lastUrl = window.location.href;
  setInterval(() => {
    if (window.location.href !== lastUrl) {
      lastUrl = window.location.href;
      createWidget();
      const cid = getChatId();
      console.log("__BAYQUS_QUERY__:" + JSON.stringify({ session: cid }));
    }
  }, 400);
})();
