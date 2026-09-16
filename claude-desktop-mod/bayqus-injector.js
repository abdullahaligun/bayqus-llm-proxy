// Bayqus Proxy Claude Desktop Main Process Injector
const { app } = require("electron");
const http = require("http");
const fs = require("fs");
const path = require("path");

const PROXY_PORT = 5199;
const UI_SCRIPT_PATH = path.join(__dirname, "bayqus-ui.js");
let uiScriptCache = null;

function getUiScript() {
  if (uiScriptCache) return uiScriptCache;
  try {
    if (fs.existsSync(UI_SCRIPT_PATH)) {
      uiScriptCache = fs.readFileSync(UI_SCRIPT_PATH, "utf8");
    }
  } catch (e) {
    console.error("[Bayqus] Failed to read bayqus-ui.js:", e);
  }
  return uiScriptCache || "";
}

function postProxy(endpoint, data, callback) {
  const payload = JSON.stringify(data || {});
  const req = http.request(
    {
      hostname: "127.0.0.1",
      port: PROXY_PORT,
      path: endpoint,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(payload),
      },
      timeout: 2000,
    },
    (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          if (callback) callback(null, JSON.parse(body));
        } catch (e) {
          if (callback) callback(null, body);
        }
      });
    }
  );
  req.on("error", (err) => {
    if (callback) callback(err);
  });
  req.write(payload);
  req.end();
}

function getProxyData(callback) {
  const req = http.get(
    {
      hostname: "127.0.0.1",
      port: PROXY_PORT,
      path: "/__bayqus/data",
      timeout: 2000,
    },
    (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        try {
          callback(null, JSON.parse(body));
        } catch (e) {
          callback(e);
        }
      });
    }
  );
  req.on("error", (err) => callback(err));
}

function syncRouteForSession(contents, sessionId) {
  if (!sessionId || sessionId === "global" || sessionId === "new") {
    getProxyData((err, data) => {
      if (!err && data && data.default_route) {
        contents.executeJavaScript(`window.__bayqusSetRoute("${data.default_route}")`).catch(() => {});
      }
    });
    return;
  }

  getProxyData((err, data) => {
    if (err || !data) return;
    const pins = (data.oturumlar && data.oturumlar.pins) || {};
    const route = pins[sessionId] || data.default_route || "abonelik";
    contents.executeJavaScript(`window.__bayqusSetRoute("${route}")`).catch(() => {});
  });
}

function setupContents(contents) {
  const script = getUiScript();
  if (!script) return;

  contents.on("did-finish-load", () => {
    contents.executeJavaScript(script).catch(() => {});
    const url = contents.getURL();
    const m = url.match(/\/chat\/([a-zA-Z0-9-]+)/);
    syncRouteForSession(contents, m ? m[1] : "new");
  });

  contents.on("did-navigate-in-page", (event, url) => {
    contents.executeJavaScript(script).catch(() => {});
    const m = url.match(/\/chat\/([a-zA-Z0-9-]+)/);
    syncRouteForSession(contents, m ? m[1] : "new");
  });

  contents.on("console-message", (event, level, message) => {
    if (typeof message !== "string") return;

    if (message.startsWith("__BAYQUS_PIN__:")) {
      try {
        const data = JSON.parse(message.substring(15));
        const session = data.session;
        const route = data.route;
        if (session && session !== "global" && session !== "new") {
          postProxy("/__bayqus/pin", { session, route });
        } else {
          postProxy("/__bayqus/default-route", { route });
        }
      } catch (e) {
        console.error("[Bayqus] Pin parse error:", e);
      }
    } else if (message.startsWith("__BAYQUS_QUERY__:")) {
      try {
        const data = JSON.parse(message.substring(17));
        syncRouteForSession(contents, data.session);
      } catch (e) {
        console.error("[Bayqus] Query parse error:", e);
      }
    }
  });
}

// Electron başlatıldığında tüm webContents'leri dinle
app.on("web-contents-created", (event, contents) => {
  setupContents(contents);
});

console.log("[Bayqus] Claude Desktop integration initialized.");
