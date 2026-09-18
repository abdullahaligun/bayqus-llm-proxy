"""Pano HTML'i. Tek dosya, disa bagimlilik yok — proxy kendisi servis eder."""

PAGE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>bayqus-proxy · Trafik Sniffer & Kontrol Merkezi</title>
<style>
:root{
  --bg:#f8fafc; --panel:#ffffff; --ink:#0f172a; --dim:#64748b; --line:#e2e8f0;
  --acc:#d97706; --acc-bg:#fef3c7; --ok:#16a34a; --ok-bg:#dcfce7;
  --warn:#ea580c; --warn-bg:#ffedd5; --bad:#dc2626; --bad-bg:#fee2e2;
  --blue:#2563eb; --blue-bg:#dbeafe; --purple:#7c3aed; --purple-bg:#f3e8ff;
  --radius:10px;
}
@media (prefers-color-scheme:dark){:root{
  --bg:#090d16; --panel:#111827; --ink:#f1f5f9; --dim:#94a3b8; --line:#1f293d;
  --acc:#f59e0b; --acc-bg:#2d2008; --ok:#22c55e; --ok-bg:#062d14;
  --warn:#f97316; --warn-bg:#331402; --bad:#ef4444; --bad-bg:#330c0c;
  --blue:#3b82f6; --blue-bg:#0c214d; --purple:#a855f7; --purple-bg:#290d4a;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font:13.5px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;
  padding:12px 24px;border-bottom:1px solid var(--line);background:var(--panel);position:sticky;top:0;z-index:50}
.brand{display:flex;align-items:center;gap:10px}
.brand h1{margin:0;font-size:17px;font-weight:700;letter-spacing:-.02em;display:flex;align-items:center;gap:8px}
.dot{width:9px;height:9px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok);display:inline-block}
.dot.warn{background:var(--warn);box-shadow:0 0 8px var(--warn)}
.dot.bad{background:var(--bad);box-shadow:0 0 8px var(--bad)}
.head-actions{display:flex;align-items:center;gap:12px;font-size:12px;flex-wrap:wrap}

/* Varsayilan Mod Secici Segment */
.default-switcher{display:flex;align-items:center;gap:4px;background:var(--bg);
  padding:3px 6px;border-radius:8px;border:1px solid var(--line)}
.default-switcher span{font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;margin-right:2px}
.def-btn{padding:4px 10px;font-size:11.5px;font-weight:600;border:1px solid transparent;
  border-radius:6px;background:none;cursor:pointer;color:var(--dim);transition:all .15s}
.def-btn:hover{color:var(--ink)}
.def-btn.active-abonelik{background:var(--ok-bg);color:var(--ok);border-color:var(--ok);box-shadow:0 0 8px rgba(22,163,74,0.2)}
.def-btn.active-gateway{background:var(--warn-bg);color:var(--warn);border-color:var(--warn);box-shadow:0 0 8px rgba(234,88,12,0.2)}

/* Nav Tabs */
nav.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);background:var(--panel);padding:0 24px;overflow-x:auto}
.tab-btn{padding:10px 16px;background:none;border:none;border-bottom:2px solid transparent;
  color:var(--dim);cursor:pointer;font-weight:600;font-size:13px;display:flex;align-items:center;gap:6px;transition:all .15s;white-space:nowrap}
.tab-btn:hover{color:var(--ink)}
.tab-btn.active{color:var(--acc);border-bottom-color:var(--acc)}

main{padding:22px 24px;max-width:1420px;margin:0 auto}
.tab-content{display:none}
.tab-content.active{display:block}

/* KPI Cards */
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-bottom:20px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.card .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.card .v{font-size:22px;font-weight:700;margin-top:3px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.card .n{color:var(--dim);font-size:11px;margin-top:2px}

/* Section styling */
h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim);
  margin:24px 0 10px;font-weight:700;display:flex;align-items:center;justify-content:space-between}
.wrap{overflow-x:auto;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{padding:8px 12px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--line)}
th{color:var(--dim);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;
  position:sticky;top:0;background:var(--panel);cursor:default}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
tr.clickable{cursor:pointer;transition:background .1s}
tr.clickable:hover{background:rgba(217,119,6,0.06)}
tr.err-row{background:rgba(220,38,38,0.06)}
tr.subagent-row{background:rgba(124,58,237,0.03)}
td{font-variant-numeric:tabular-nums}

/* Badges & Tags */
.badge{display:inline-block;padding:2px 7px;border-radius:12px;font-size:11px;font-weight:600;line-height:1.2}
.badge-ok{background:var(--ok-bg);color:var(--ok);border:1px solid var(--ok)}
.badge-bad{background:var(--bad-bg);color:var(--bad);border:1px solid var(--bad)}
.badge-warn{background:var(--warn-bg);color:var(--warn);border:1px solid var(--warn)}
.badge-blue{background:var(--blue-bg);color:var(--blue);border:1px solid var(--blue)}
.badge-purple{background:var(--purple-bg);color:var(--purple);border:1px solid var(--purple)}
.badge-dim{background:var(--bg);color:var(--dim);border:1px solid var(--line)}

.ok{color:var(--ok)} .warn{color:var(--warn)} .bad{color:var(--bad)} .acc{color:var(--acc)}
.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11.5px}
.bar{height:4px;background:var(--line);border-radius:2px;overflow:hidden;margin-top:5px}
.bar>i{display:block;height:100%;background:var(--acc)}
.empty{padding:36px;text-align:center;color:var(--dim)}

/* Controls & Buttons */
select,input[type="text"],textarea{font:inherit;font-size:12.5px;padding:6px 10px;border-radius:6px;
  border:1px solid var(--line);background:var(--panel);color:var(--ink)}
select:focus,input[type="text"]:focus,textarea:focus{outline:none;border-color:var(--acc)}
button{font:inherit;font-size:12px;padding:5px 12px;border-radius:6px;font-weight:600;
  border:1px solid var(--line);background:var(--panel);color:var(--ink);cursor:pointer;transition:all .15s}
button:hover{border-color:var(--acc);color:var(--acc)}
button.primary{background:var(--acc);color:#fff;border-color:var(--acc)}
button.primary:hover{opacity:.9}
button.danger{background:var(--bad-bg);color:var(--bad);border-color:var(--bad)}
button.danger:hover{background:var(--bad);color:#fff}
button.sm{padding:2px 7px;font-size:11px}
.btn-group{display:inline-flex;gap:4px}

/* Toggle Switch */
.switch{position:relative;display:inline-block;width:34px;height:19px}
.switch input{opacity:0;width:0;height:0}
.slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;background-color:var(--line);
  transition:.2s;border-radius:19px}
.slider:before{position:absolute;content:"";height:13px;width:13px;left:3px;bottom:3px;
  background-color:#fff;transition:.2s;border-radius:50%}
input:checked + .slider{background-color:var(--ok)}
input:checked + .slider:before{transform:translateX(15px)}

/* Filter Bar */
.filter-bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px;
  background:var(--panel);padding:10px 14px;border:1px solid var(--line);border-radius:var(--radius)}

/* Modals */
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.55);
  display:none;align-items:center;justify-content:center;z-index:100;backdrop-filter:blur(2px)}
.modal-overlay.active{display:flex}
.modal{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  max-width:780px;width:92%;max-height:88vh;overflow-y:auto;box-shadow:0 20px 40px rgba(0,0,0,0.3);padding:22px}
.modal-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.modal-title{margin:0;font-size:16px;font-weight:700}
.close-btn{background:none;border:none;font-size:20px;cursor:pointer;color:var(--dim);padding:0 4px}
.form-row{margin-bottom:13px}
.form-row label{display:block;font-size:11.5px;font-weight:600;color:var(--dim);margin-bottom:4px;text-transform:uppercase}
.form-row input,.form-row select,.form-row textarea{width:100%}

/* Route Card List */
.route-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px;margin-bottom:12px;display:flex;flex-direction:column;gap:10px}
.route-card.disabled{opacity:0.65;border-style:dashed}
.route-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.route-name{font-size:14px;font-weight:700;display:flex;align-items:center;gap:8px}
.route-details{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:12px}

/* Group Card Styling */
.group-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);margin-bottom:18px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.02)}
.group-header{padding:12px 18px;background:rgba(217,119,6,0.04);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}
.group-title{font-weight:700;font-size:14.5px;display:flex;align-items:center;gap:8px}
.group-controls{display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:12px}

/* MCP Management Styling */
.mcp-bar{padding:10px 18px;background:rgba(0,0,0,0.02);border-bottom:1px solid var(--line);font-size:12px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.mcp-server-item{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:8px 12px;display:flex;align-items:flex-start;gap:8px;font-size:11.5px;transition:background 0.15s}
.mcp-server-item:hover{background:var(--bg2)}
.mcp-server-item.disabled{opacity:0.65;background:var(--bg)}
</style>
</head>
<body>

<header>
  <div class="brand">
    <span class="dot" id="live-dot"></span>
    <h1>🦉 bayqus-proxy</h1>
    <span class="badge badge-dim" id="mode-badge">MOD: ...</span>
    <span class="badge badge-dim">PORT: 5199</span>
  </div>

  <div class="head-actions">
    <!-- 1-Click Varsayılan Mod Değiştirici -->
    <div class="default-switcher">
      <span>Varsayılan Mod:</span>
      <button type="button" id="btn-def-abonelik" class="def-btn" onclick="setDefaultRoute('abonelik')">
        🟢 Abonelik (Anthropic)
      </button>
      <button type="button" id="btn-def-gateway" class="def-btn" onclick="setDefaultRoute('gateway')">
        🏢 Gateway (Şirket)
      </button>
    </div>

    <span id="last-update" class="mono">yükleniyor…</span>
    <label style="display:flex;align-items:center;gap:5px;cursor:pointer">
      <input type="checkbox" id="auto-refresh" checked> Canlı (4s)
    </label>
    <button onclick="tick(true)" class="sm">Yenile 🔄</button>
  </div>
</header>

<nav class="tabs">
  <button class="tab-btn active" data-tab="tab-sessions">💬 Oturumlar & Proje Yönlendirmesi</button>
  <button class="tab-btn" data-tab="tab-traffic">🚦 Trafik & Sniffer Log</button>
  <button class="tab-btn" data-tab="tab-history" onclick="loadHistory()">📜 İstek Geçmişi & Mesajlar (Son 5000)</button>
  <button class="tab-btn" data-tab="tab-analytics">📊 Analiz & Metrikler</button>
  <button class="tab-btn" data-tab="tab-routes">⚙️ Rota Tanımları</button>
  <button class="tab-btn" data-tab="tab-summarizer">🧠 Akıllı Özetleyici & Prefix Cache</button>
</nav>

<main>

  <!-- TAB 1: OTURUMLAR & PROJELER -->
  <section id="tab-sessions" class="tab-content active">
    <!-- Bilgi ve Çözümleme Hiyerarşisi -->
    <div style="background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 18px;margin-bottom:20px">
      <div style="font-weight:700;font-size:14px;margin-bottom:6px">💡 Claude Desktop Sol Panel Entegrasyonu (Grup & Sohbet Yönetimi)</div>
      <div style="font-size:12.5px;color:var(--dim);line-height:1.6">
        Claude Desktop sol panelindeki <b>grupları</b> ve <b>sohbetleri</b> doğrudan buradan yönetebilirsiniz.<br>
        🛡️ <b>Alt-Ajanlar (Sub-Agents):</b> Geçici oldukları için ana listeyi kalabalıklaştırmaz. Her sohbetin veya grubun alt-ajanlarının nereye gideceğini (ana sohbetle aynı, gateway veya abonelik) bağımsız olarak seçebilirsiniz.<br>
        <b>Yönlendirme Öncelik Sırası:</b>
        <ol style="margin:6px 0 2px 18px;padding:0">
          <li><b>Sohbet Özel Kuralı</b> (o sohbete özel belirlenen rota)</li>
          <li><b>Grup Kuralı</b> (o grubun altındaki tüm sohbetler ve alt-ajanlar)</li>
          <li><b>Proje Klasör Kuralı</b> (disk klasörü eşleşmesi)</li>
          <li><b>Varsayılan Mod</b> (hiçbir kural eşleşmezse: <b id="info-def-route" class="acc">gateway</b>)</li>
        </ol>
      </div>
    </div>

    <h2>📂 Claude Desktop Grupları & Sohbetleri</h2>
    <div id="claude-groups-wrap" style="margin-bottom:28px"></div>

    <h2>Aktif Sohbet Oturumları (Son Trafik)</h2>
    <div class="wrap" id="sessions-wrap" style="margin-bottom:28px"></div>

    <details style="margin-bottom:24px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:12px 16px">
      <summary style="cursor:pointer;font-weight:700;font-size:13px;color:var(--dim)">📁 Gelişmiş: Klasör Bazlı Proje Kuralları (Disk Yolları)</summary>
      <div style="margin:14px 0 10px;display:flex;gap:10px;align-items:center">
        <input type="text" id="project-search" placeholder="Proje klasörü ara (örn: bayqus, frontend, backend)..." style="min-width:280px">
        <span class="dim mono" id="project-count-lbl"></span>
      </div>
      <div class="wrap" id="project-pins-wrap"></div>
    </details>
  </section>

  <!-- TAB 2: TRAFİK & SNIFFER LOG -->
  <section id="tab-traffic" class="tab-content">
    <div class="filter-bar">
      <input type="text" id="traffic-search" placeholder="Ara (model, rota, hata, oturum, altajan)..." style="min-width:240px">
      <select id="traffic-filter-status">
        <option value="">Durum: Tümü</option>
        <option value="ok">Yalnızca Başarılı (200 OK)</option>
        <option value="err">Yalnızca Hatalar (502 / 4xx)</option>
        <option value="mock">Güvenlik Takliti (Mock)</option>
      </select>
      <select id="traffic-filter-agent">
        <option value="">Ajan Türü: Tümü</option>
        <option value="sub">🤖 Yalnızca Alt-Ajanlar (Sub-Agents)</option>
        <option value="main">👤 Yalnızca Ana Oturumlar</option>
      </select>
      <select id="traffic-filter-model">
        <option value="">Model: Tümü</option>
      </select>
      <select id="traffic-filter-route">
        <option value="">Rota: Tümü</option>
      </select>
      <span style="flex:1"></span>
      <span class="mono" id="traffic-count-label">0 istek</span>
    </div>

    <div class="wrap">
      <table>
        <thead>
          <tr>
            <th>Saat</th>
            <th>Durum</th>
            <th>Model</th>
            <th>Tür</th>
            <th>Rota</th>
            <th>Upstream</th>
            <th>Süre</th>
            <th>Mesaj</th>
            <th>Bağlam</th>
            <th>Çıktı</th>
            <th>İsabet %</th>
            <th>Budama</th>
            <th>Maliyet</th>
            <th>İncele</th>
          </tr>
        </thead>
        <tbody id="traffic-rows">
          <tr><td colspan="14" class="empty">Yükleniyor…</td></tr>
        </tbody>
      </table>
    </div>
  </section>

  <!-- TAB 3: ANALİZ & METRİKLER -->
  <section id="tab-analytics" class="tab-content">
    <div class="grid" id="analytics-kpis"></div>

    <h2>Token Dağılımı & Özet</h2>
    <div class="card" id="token-dist-card" style="margin-bottom:20px">
      <div style="font-size:12px;color:var(--dim);margin-bottom:8px">Toplam Token Dağılımı</div>
      <div style="height:12px;border-radius:6px;display:flex;overflow:hidden;background:var(--line)" id="token-dist-bar">
        <div style="background:var(--ok);width:0%" id="td-read" title="Cache Read"></div>
        <div style="background:var(--blue);width:0%" id="td-inp" title="Input"></div>
        <div style="background:var(--purple);width:0%" id="td-out" title="Output"></div>
      </div>
      <div style="display:flex;gap:18px;margin-top:8px;font-size:11.5px;color:var(--dim);flex-wrap:wrap">
        <span><b class="ok">■</b> Cache Read: <span id="td-read-lbl">0</span></span>
        <span><b style="color:var(--blue)">■</b> Yeni Girdi: <span id="td-inp-lbl">0</span></span>
        <span><b style="color:var(--purple)">■</b> Model Çıktısı: <span id="td-out-lbl">0</span></span>
      </div>
    </div>

    <h2>Model Bazlı Dağılım</h2>
    <div class="wrap" id="model-table-wrap" style="margin-bottom:20px"></div>

    <h2>Rota Bazlı Dağılım</h2>
    <div class="wrap" id="route-table-wrap" style="margin-bottom:20px"></div>

    <h2>Günlük Trafik & Token Hacmi</h2>
    <div class="wrap" id="day-table-wrap"></div>
  </section>

  <!-- TAB 4: ROTA TANIMLARI -->
  <section id="tab-routes" class="tab-content">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <h3 style="margin:0;font-size:16px">Tanımlı Rotalar</h3>
        <span style="font-size:12px;color:var(--dim)">Proxy üzerinde kullanabileceğiniz hedefler ve ayarlar.</span>
      </div>
      <div style="display:flex;gap:10px">
        <button onclick="openJsonModal()" class="sm">JSON Olarak Düzenle 📝</button>
        <button onclick="openNewRouteModal()" class="primary sm">+ Yeni Rota Ekle</button>
      </div>
    </div>

    <!-- Proxy Motor Ayarları -->
    <div class="card" style="margin-bottom:24px;display:flex;gap:24px;align-items:center;flex-wrap:wrap">
      <div>
        <label style="font-size:11px;color:var(--dim);font-weight:600;display:block;margin-bottom:4px">BUDAMA MODU (PRUNER)</label>
        <select id="config-mode" onchange="updateProxyConfig()">
          <option value="prune">prune (Aktif Budama - Token Tasarruflu)</option>
          <option value="shadow">shadow (Gölge Modu - Göndermeden Ölç)</option>
          <option value="passthrough">passthrough (Düz Geçiş - Dokunma)</option>
        </select>
      </div>
      <div>
        <label style="font-size:11px;color:var(--dim);font-weight:600;display:block;margin-bottom:4px">GÜVENLİK SINIFLANDIRICI TAKLİTİ (MOCK)</label>
        <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;cursor:pointer">
          <input type="checkbox" id="config-mock" onchange="updateProxyConfig()">
          <span>Aktif (max_tokens ≤ 64 hızlı güvenlik sorgularını yerel karşıla)</span>
        </label>
      </div>
    </div>

    <h2>Varsayılan Rota (Fallback Modu)</h2>
    <div class="card" id="default-route-card" style="margin-bottom:24px"></div>

    <h2>Yapılandırılmış Rotalar (routes.json)</h2>
    <div id="routes-list"></div>
  </section>

  <!-- TAB 5: AKILLI ÖZETLEYİCİ & PREFIX CACHE -->
  <section id="tab-summarizer" class="tab-content">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <h3 style="margin:0;font-size:16px">🧠 Akıllı Özetleyici & Kalıcı Prefix Cache</h3>
        <span style="font-size:12px;color:var(--dim)">Antigravity Alt Ajanı ve Google AI Studio (Gemini 3.1 Flash-Lite) ile otomatik bağlam sıkıştırma ve önbellekleme.</span>
      </div>
      <div style="display:flex;gap:10px">
        <button type="button" onclick="testGeminiApi()" class="sm">Gemini Bağlantısını Test Et ⚡</button>
        <button type="button" onclick="clearPrefixCache()" class="sm danger">Önbelleği Boşalt 🗑️</button>
      </div>
    </div>

    <!-- KPI Grid -->
    <div class="grid">
      <div class="card">
        <div class="k">Prefix Önbellek Kaydı</div>
        <div class="v" id="kpi-cache-entries">0</div>
        <div class="n">SQLite kalıcı önbellek</div>
      </div>
      <div class="card">
        <div class="k">Önbellek İsabeti (Hits)</div>
        <div class="v ok" id="kpi-cache-hits">0</div>
        <div class="n">0.1 ms anında yanıt</div>
      </div>
      <div class="card">
        <div class="k">Budanan Toplam Token</div>
        <div class="v ok" id="kpi-cache-tokens">0</div>
        <div class="n" id="kpi-cache-bytes">0 KB Tasarruf</div>
      </div>
      <div class="card">
        <div class="k">Antigravity Ajan Kuyruğu</div>
        <div class="v" id="kpi-agent-queue">0 / 0</div>
        <div class="n">Bekleyen / Hazır Özet</div>
      </div>
    </div>

    <!-- Ayarlar Kartı -->
    <div class="card" style="margin-bottom:24px">
      <div style="font-weight:700;font-size:14px;margin-bottom:12px">⚙️ Özetleyici Motor Ayarları</div>
      <form id="summarizer-form" onsubmit="saveSummarizerSettings(event)">
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px">
          <div class="form-row">
            <label>Özetleme Modu</label>
            <select id="sum-mode">
              <option value="hybrid">🌟 Hibrit (Önce Antigravity Ajanı, Fallback Gemini Flash-Lite)</option>
              <option value="agent_only">🤖 Yalnızca Antigravity Ajanı (Dosya Köprüsü)</option>
              <option value="api_only">⚡ Yalnızca Google AI Studio API</option>
              <option value="deterministic">✂️ Deterministik Budama (AI Özetleme Kapalı)</option>
            </select>
          </div>

          <div class="form-row">
            <label>Tercih Edilen Gemini Modeli (Fallback)</label>
            <select id="sum-model">
              <option value="round-robin">🔄 Sırayla Dön (En İyiden En Kötüye Round-Robin - Sıfır Rate Limit)</option>
              <option value="best-to-worst">⚡ En İyiden En Kötüye Öncelikli (Waterfall - Kotası Bittikçe Düş)</option>
              <option value="gemini-3.5-flash">1. gemini-3.5-flash (En Yüksek Kalite Tam Flash)</option>
              <option value="gemini-3-flash-preview">2. gemini-3-flash-preview (Gemini 3 Flash)</option>
              <option value="gemini-3.5-flash-lite">3. gemini-3.5-flash-lite (15 RPM / 500 RPD - Yeni Nesil)</option>
              <option value="gemini-3.1-flash-lite">4. gemini-3.1-flash-lite (15 RPM / 500 RPD - Kanıtlanmış)</option>
              <option value="gemini-3.6-flash">5. gemini-3.6-flash (5 RPM / 20 RPD)</option>
              <option value="gemini-3.7-flash">6. gemini-3.7-flash (Akıl Yürütme)</option>
              <option value="gemini-3.8-flash">7. gemini-3.8-flash (Akıl Yürütme)</option>
              <option value="gemini-flash-latest">8. gemini-flash-latest (Son Sürüm)</option>
            </select>
          </div>

          <div class="form-row">
            <label>Dondurma Blok Boyutu (BLOCK_SIZE)</label>
            <select id="sum-block">
              <option value="16">16 Mesaj (Önerilen: 16 tur boyunca %95+ Cache Hit)</option>
              <option value="8">8 Mesaj</option>
              <option value="24">24 Mesaj</option>
            </select>
          </div>

          <div class="form-row">
            <label>Aktif Tutulacak Son Mesaj Sayısı (KEEP_RECENT)</label>
            <input type="number" id="sum-keep-recent" min="8" max="60" value="24">
          </div>
        </div>

        <div class="form-row" style="margin-top:10px">
          <label>Google AI Studio API Anahtarı</label>
          <div style="display:flex;gap:10px">
            <input type="password" id="sum-api-key" placeholder="AIzaSy... veya AQ.Ab8..." style="flex:1">
            <button type="button" class="sm" onclick="toggleApiKeyVisibility()">👁️ Göster/Gizle</button>
          </div>
          <small class="dim">Ücretsiz kota: Günlük 1.500 istek. Boş bırakılırsa yalnızca Antigravity ajanı veya deterministik budama çalışır.</small>
        </div>

        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:16px">
          <button type="submit" class="primary">Özetleyici Ayarlarını Kaydet</button>
        </div>
      </form>
    </div>

    <!-- Antigravity Ajan Kuyruğu Tablosu -->
    <h2>Antigravity Ajan Kuyruğu (Bekleyen Özet İstekleri)</h2>
    <div id="pending-summaries-wrap"></div>
  <!-- TAB: İSTEK GEÇMİŞİ & MESAJ İÇERİKLERİ (SON 5000) -->
  <section id="tab-history" class="tab-content">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div style="display:flex;align-items:center;gap:10px;flex:1;max-width:650px">
        <input type="text" id="hist-search" placeholder="Mesaj içeriğinde, yanıtta veya sistem yönergesinde ara..." style="flex:1" onkeydown="if(event.key==='Enter')loadHistory(0)">
        <button class="primary" onclick="loadHistory(0)">🔍 Ara</button>
        <button onclick="document.getElementById('hist-search').value='';loadHistory(0)">Temizle</button>
      </div>
      <div style="display:flex;gap:8px;align-items:center">
        <span id="hist-total-badge" class="badge badge-dim">Toplam: 0</span>
        <button onclick="loadHistory(CURRENT_HIST_OFFSET)">🔄 Yenile</button>
        <button class="danger" onclick="clearAllHistory()">🗑️ Geçmişi Sıfırla</button>
      </div>
    </div>

    <div class="wrap">
      <table id="hist-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Zaman</th>
            <th>Durum</th>
            <th>Süre</th>
            <th style="text-align:left">Model</th>
            <th>Girdi</th>
            <th>Çıktı</th>
            <th>Önbellek</th>
            <th>Boyut</th>
            <th>Oturum</th>
            <th>İşlem</th>
          </tr>
        </thead>
        <tbody id="hist-tbody">
          <tr><td colspan="11" class="empty">İstek geçmişi yükleniyor...</td></tr>
        </tbody>
      </table>
    </div>

    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:14px">
      <div id="hist-page-info" class="dim mono" style="font-size:12px"></div>
      <div class="btn-group">
        <button id="hist-prev-btn" onclick="prevHistoryPage()" disabled>⬅️ Önceki</button>
        <button id="hist-next-btn" onclick="nextHistoryPage()" disabled>Sonraki ➡️</button>
      </div>
    </div>
  </section>

</main>

<!-- MODAL: İSTEK DETAY İNCELEYİCİ (INSPECTOR) -->
<div class="modal-overlay" id="inspector-modal" onclick="if(event.target===this)closeModal('inspector-modal')">
  <div class="modal">
    <div class="modal-header">
      <h3 class="modal-title" id="insp-title">İstek Detayı</h3>
      <button class="close-btn" onclick="closeModal('inspector-modal')">&times;</button>
    </div>
    <div id="insp-content"></div>
  </div>
</div>

<!-- MODAL: GEÇMİŞ İSTEK VE YANIT DETAYI -->
<div class="modal-overlay" id="history-modal" onclick="if(event.target===this)closeModal('history-modal')">
  <div class="modal" style="max-width:950px;max-height:90vh;display:flex;flex-direction:column">
    <div class="modal-header">
      <h3 class="modal-title" id="hist-modal-title">İstek ve Yanıt İçeriği</h3>
      <button class="close-btn" onclick="closeModal('history-modal')">&times;</button>
    </div>
    <div id="hist-modal-body" style="overflow-y:auto;flex:1;padding-right:8px"></div>
  </div>
</div>

<!-- MODAL: YENİ / DÜZENLE ROTA -->
<div class="modal-overlay" id="route-modal" onclick="if(event.target===this)closeModal('route-modal')">
  <div class="modal">
    <div class="modal-header">
      <h3 class="modal-title" id="route-modal-title">Rota Düzenle</h3>
      <button class="close-btn" onclick="closeModal('route-modal')">&times;</button>
    </div>
    <form id="route-form" onsubmit="saveRouteForm(event)">
      <div class="form-row">
        <label>Rota Adı (Tekil İsim)</label>
        <input type="text" id="rf-name" required placeholder="örnek: gateway">
      </div>
      <div class="form-row">
        <label>Upstream URL</label>
        <input type="text" id="rf-upstream" required placeholder="https://api.anthropic.com veya https://...">
      </div>
      <div class="form-row">
        <label>Model Eşleşme Kalıpları (Virgülle ayırın, boş bırakırsanız modele göre kısıtlamaz)</label>
        <input type="text" id="rf-contains" placeholder="boş bırakılabilir">
      </div>
      <div class="form-row">
        <label>Kimlik Doğrulama (Auth)</label>
        <select id="rf-auth-type" onchange="toggleAuthFields()">
          <option value="passthrough">passthrough (Gelen OAuth aynen geçer — api.anthropic.com için)</option>
          <option value="strip">strip (Kimlik başlıklarını düşür)</option>
          <option value="file">file (JSON profilinden/ayar dosyasından oku)</option>
          <option value="env">env (Ortam değişkeninden oku)</option>
        </select>
      </div>
      <div id="rf-auth-file-box" class="form-row" style="display:none">
        <label>Profil JSON Dosyası Yolu</label>
        <input type="text" id="rf-auth-file" placeholder="/path/to/credentials.json">
        <label style="margin-top:6px">JSON Anahtarı</label>
        <input type="text" id="rf-auth-key" placeholder="apiKey">
      </div>
      <div id="rf-auth-env-box" class="form-row" style="display:none">
        <label>Ortam Değişkeni Adı</label>
        <input type="text" id="rf-auth-env" placeholder="ANTHROPIC_API_KEY veya BAYQUS_GATEWAY_KEY">
      </div>
      <div class="form-row">
        <label>Model Yeniden Yazma (İsteğe bağlı model_rewrite)</label>
        <input type="text" id="rf-rewrite" placeholder="boş bırakılabilir">
      </div>
      <div class="form-row" style="display:flex;gap:18px;align-items:center;margin-top:14px">
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;margin:0">
          <input type="checkbox" id="rf-enabled" checked> Rota Aktif (enabled)
        </label>
        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;margin:0">
          <input type="checkbox" id="rf-prune" checked> Budama Yap (prune)
        </label>
      </div>
      <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px">
        <button type="button" onclick="closeModal('route-modal')">İptal</button>
        <button type="submit" class="primary">Kaydet & Uygula</button>
      </div>
    </form>
  </div>
</div>

<!-- MODAL: RAW JSON EDIT -->
<div class="modal-overlay" id="json-modal" onclick="if(event.target===this)closeModal('json-modal')">
  <div class="modal" style="max-width:850px">
    <div class="modal-header">
      <h3 class="modal-title">routes.json Doğrudan Düzenleme</h3>
      <button class="close-btn" onclick="closeModal('json-modal')">&times;</button>
    </div>
    <div class="form-row">
      <textarea id="json-editor" rows="18" class="mono" style="width:100%;font-size:12px"></textarea>
    </div>
    <div style="display:flex;justify-content:flex-end;gap:10px">
      <button type="button" onclick="closeModal('json-modal')">İptal</button>
      <button type="button" class="primary" onclick="saveJsonConfig()">Kaydet ve Canlı Uygula</button>
    </div>
  </div>
</div>

<script>
const N = x => (x??0).toLocaleString('tr-TR');
const USD = x => '$' + (x??0).toLocaleString('tr-TR',{minimumFractionDigits:2,maximumFractionDigits:2});
const USD4 = x => '$' + (x??0).toLocaleString('tr-TR',{minimumFractionDigits:4,maximumFractionDigits:4});
const esc = s => String(s??'').replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));

let LATEST_DATA = null;

// Tab Nav
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
  });
});

function openModal(id){ document.getElementById(id).classList.add('active'); }
function closeModal(id){ document.getElementById(id).classList.remove('active'); }

function toggleAuthFields(){
  const t = document.getElementById('rf-auth-type').value;
  document.getElementById('rf-auth-file-box').style.display = (t==='file')?'block':'none';
  document.getElementById('rf-auth-env-box').style.display = (t==='env')?'block':'none';
}

// Set Default Route (Varsayılan Mod)
async function setDefaultRoute(routeName){
  try{
    const r = await fetch('/__bayqus/default-route', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({route: routeName})
    });
    const j = await r.json();
    if(!j.ok){
      alert('Varsayılan mod değiştirilemedi: ' + j.mesaj);
    }
    tick(true);
  }catch(e){
    alert('Hata: ' + e.message);
  }
}

// Render Dashboard
function renderAll(d){
  LATEST_DATA = d;
  const runtime = d.runtime_config || {};
  const routesCfg = d.routes_config || {};
  const defRoute = d.default_route || routesCfg.default?.name || 'abonelik';

  // Header status & Varsayilan Mod Buttons
  document.getElementById('last-update').textContent = `Güncellendi: ${d.guncellendi || '—'}`;
  document.getElementById('mode-badge').textContent = `MOD: ${(runtime.mode||'prune').toUpperCase()}`;
  document.getElementById('mode-badge').className = `badge ${runtime.mode==='prune'?'badge-ok':'badge-warn'}`;
  document.getElementById('config-mode').value = runtime.mode || 'prune';
  document.getElementById('config-mock').checked = !!runtime.mock_classifier;

  const btnAbonelik = document.getElementById('btn-def-abonelik');
  const btnGateway = document.getElementById('btn-def-gateway');
  if(defRoute === 'gateway'){
    btnGateway.className = 'def-btn active-gateway';
    btnAbonelik.className = 'def-btn';
  } else {
    btnAbonelik.className = 'def-btn active-abonelik';
    btnGateway.className = 'def-btn';
  }
  const infoDef = document.getElementById('info-def-route');
  if(infoDef){
    infoDef.textContent = defRoute;
    infoDef.className = defRoute === 'gateway' ? 'warn' : 'ok';
  }

  // Render Tabs
  renderSessionsTab(d, defRoute);
  renderTrafficTable(d.son || []);
  renderAnalytics(d);
  renderRoutesTab(routesCfg, d.rotalar || [], defRoute);
  renderSummarizerTab(d);
}

// 1. SESSIONS & PROJECTS TAB
function renderSessionsTab(d, defRoute){
  const ses = d.oturumlar || [];
  const rotalar = d.rotalar || [];
  const pk = d.proje_kurallari || {};
  const claudeGroups = d.claude_groups || [];

  // --- A. Render Claude Desktop Groups & Chats (Sol Panel) ---
  const gWrap = document.getElementById('claude-groups-wrap');
  if(gWrap){
    if(!claudeGroups.length){
      gWrap.innerHTML = '<div class="card empty">Claude Desktop sol panelinde tanımlı grup/sohbet bulunamadı.</div>';
    } else {
      gWrap.innerHTML = claudeGroups.map(g => {
        const gCur = g.sabit || '';
        const gSubCur = g.subagent_sabit || '';

        // Options for group route
        const gOpts = [`<option value="">— Varsayılan (${esc(defRoute)}) —</option>`]
          .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===gCur?' selected':''}>${
            x.ad==='gateway' ? '🏢 gateway (Şirket Gateway)' : x.ad==='abonelik' ? '🟢 abonelik (Anthropic Resmi)' : esc(x.ad)
          }</option>`)).join('');

        // Options for group subagent route
        const gSubOpts = [`<option value="">— 🔗 Ana Sohbetle Aynı (${esc(g.etkin)}) —</option>`]
          .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===gSubCur?' selected':''}>${
            x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
          }</option>`)).join('');

        const gBadge = g.etkin === 'gateway'
          ? '<span class="badge badge-warn">🏢 gateway</span>'
          : g.etkin === 'abonelik'
          ? '<span class="badge badge-ok">🟢 abonelik</span>'
          : `<span class="badge badge-dim">${esc(g.etkin)}</span>`;

        // Render chats inside this group
        const sRows = (g.sessions || []).map(s => {
          const sCur = s.sabit || '';
          const sSubCur = s.subagent_sabit || '';

          // Session route dropdown
          const sOpts = [`<option value="">— Gruptan Devral (${esc(g.etkin)}) —</option>`]
            .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===sCur?' selected':''}>${
              x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
            }</option>`)).join('');

          // Session subagent dropdown
          const sSubOpts = [`<option value="">— 🔗 Ana Sohbetle Aynı (${esc(s.etkin)}) —</option>`]
            .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===sSubCur?' selected':''}>${
              x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
            }</option>`)).join('');

          const sBadge = s.etkin === 'gateway'
            ? '<span class="badge badge-warn">🏢 gateway</span>'
            : s.etkin === 'abonelik'
            ? '<span class="badge badge-ok">🟢 abonelik</span>'
            : `<span class="badge badge-dim">${esc(s.etkin)}</span>`;

          const subBadge = s.subagent_etkin === 'gateway'
            ? '<span class="badge badge-warn">🏢 gateway</span>'
            : s.subagent_etkin === 'abonelik'
            ? '<span class="badge badge-ok">🟢 abonelik</span>'
            : `<span class="badge badge-dim">${esc(s.subagent_etkin)}</span>`;

          const yas = s.yas_sn == null ? '—'
            : s.yas_sn < 90 ? '<span class="ok">şimdi</span>'
            : s.yas_sn < 3600 ? Math.round(s.yas_sn/60) + ' dk önce'
            : Math.round(s.yas_sn/3600) + ' sa önce';

          const quickBtns = `
            <div class="btn-group">
              <button class="sm ${sCur==='abonelik'?'primary':''}" onclick="pinSessionDirect('${esc(s.id)}', 'abonelik')" title="Abonelik">🟢</button>
              <button class="sm ${sCur==='gateway'?'primary':''}" onclick="pinSessionDirect('${esc(s.id)}', 'gateway')" title="Gateway">🏢</button>
              ${sCur ? `<button class="sm danger" onclick="pinSessionDirect('${esc(s.id)}', '')" title="Gruba devret">↺</button>` : ''}
            </div>
          `;

          return [
            `<div><b>💬 ${esc(s.title)}</b><div class="dim mono" style="font-size:10.5px">${esc(s.cwd)}</div></div>`,
            sBadge + `<div class="dim" style="font-size:10.5px">${esc(s.kaynak)}</div>`,
            `<select data-sid="${esc(s.id)}">${sOpts}</select>`,
            `<div><select data-sub-sid="${esc(s.id)}">${sSubOpts}</select><div class="dim" style="font-size:10.5px;margin-top:2px">${esc(s.subagent_kaynak)}</div></div>`,
            `<span>${N(s.istek)} istek · ${yas}</span>`,
            quickBtns
          ];
        });

        const sTableHtml = renderSimpleTable(
          ['Sohbet Adı & Klasör', 'Geçerli Rota', 'Sohbet Rotası', 'Alt-Ajan (Sub-Agent) Rotası', 'Durum', 'Hızlı'],
          sRows
        );

        const mcpInfo = (d.groups_mcp || {})[g.name] || {};
        const mcpServers = mcpInfo.servers || [];
        const disCount = mcpInfo.disabled_count || 0;

        const mcpServersHtml = mcpServers.map(srv => {
          const isDis = srv.disabled;
          const badge = isDis 
            ? '<span class="badge badge-warn" style="font-size:10px">⊘ Devre Dışı</span>' 
            : '<span class="badge badge-ok" style="font-size:10px">✓ Aktif</span>';
          return `
            <div class="mcp-server-item ${isDis ? 'disabled' : ''}">
              <input type="checkbox" id="mcp-${esc(g.name)}-${esc(srv.id)}" 
                     ${!isDis ? 'checked' : ''} 
                     onchange="toggleMcpServer('${esc(g.name)}', '${esc(srv.id)}', !this.checked)" style="cursor:pointer;margin-top:2px">
              <div style="flex:1">
                <label for="mcp-${esc(g.name)}-${esc(srv.id)}" style="cursor:pointer;font-weight:600">
                  ${esc(srv.display_name)}
                </label>
                <div class="dim" style="font-size:10.5px;margin-top:2px">${esc(srv.description)} · <span class="mono">${esc(srv.tokens_est)}</span></div>
              </div>
              <div>${badge}</div>
            </div>
          `;
        }).join('');

        const mcpSectionHtml = `
          <div class="mcp-bar">
            <div style="display:flex;align-items:center;gap:8px">
              <span>🛠️ <b>Araç & MCP Yönetimi:</b></span>
              <span class="badge ${disCount > 0 ? 'badge-ok' : 'badge-warn'}">
                ${disCount > 0 ? `🛡️ ${disCount} sunucu kapalı (Ofis araçları context'ten çıkarıldı)` : '⚠️ Tüm araçlar açık (189+ araç, 119k context)'}
              </span>
            </div>
            <div class="btn-group">
              <button class="sm primary" onclick="applyMcpPreset('${esc(g.name)}', 'code')" title="Microsoft 365, Google Drive, Calendar, Gmail ve Obsidian'ı kapatır; ~119k context tasarrufu sağlar">🚀 Kodlama Modu (~119k Tasarruf)</button>
              <button class="sm" onclick="applyMcpPreset('${esc(g.name)}', 'all')" title="Tüm MCP sunucularını açar">🏢 Tümünü Aç</button>
            </div>
          </div>
          <details style="padding:10px 18px;background:var(--bg);border-bottom:1px solid var(--line);font-size:12px">
            <summary style="cursor:pointer;color:var(--dim);font-weight:600">⚙️ Sunucu Bazlı İnce Ayar (${mcpServers.length} MCP Sunucusu Tanımlı)</summary>
            <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(310px, 1fr));gap:8px;margin-top:10px">
              ${mcpServersHtml || '<div class="dim">Tanımlı MCP sunucusu bulunamadı.</div>'}
            </div>
          </details>
        `;

        return `
          <div class="group-card">
            <div class="group-header">
              <div class="group-title">
                <span>📁 <b>${esc(g.name)}</b></span>
                <span class="badge badge-dim">${(g.sessions || []).length} sohbet</span>
                ${gBadge}
              </div>
              <div class="group-controls">
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="dim" style="font-weight:600">Grup Rotası:</span>
                  <select data-group="${esc(g.name)}">${gOpts}</select>
                </div>
                <div style="display:flex;align-items:center;gap:6px">
                  <span class="dim" style="font-weight:600">Alt-Ajan Rotası:</span>
                  <select data-group-sub="${esc(g.name)}">${gSubOpts}</select>
                </div>
                <div class="btn-group">
                  <button class="sm ${gCur==='abonelik'?'primary':''}" onclick="pinGroupDirect('${esc(g.name)}', 'abonelik')">🟢 Abonelik</button>
                  <button class="sm ${gCur==='gateway'?'primary':''}" onclick="pinGroupDirect('${esc(g.name)}', 'gateway')">🏢 Gateway</button>
                  ${gCur ? `<button class="sm danger" onclick="pinGroupDirect('${esc(g.name)}', '')" title="Varsayılana sıfırla">↺</button>` : ''}
                </div>
              </div>
            </div>
            ${mcpSectionHtml}
            ${sTableHtml}
          </div>
        `;
      }).join('');
    }
  }

  // --- B. Render Active Sessions Table (Sadece Gerçek Sohbetler, Alt-Ajanlar Gizli) ---
  const sWrap = document.getElementById('sessions-wrap');
  if(!ses.length){
    sWrap.innerHTML = '<div class="card empty">Aktif oturum kaydı bulunmuyor.</div>';
  } else {
    const sRows = ses.map(r => {
      const opts = ['<option value="">— Proje / Varsayılan Kuralına Bırak —</option>']
        .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===r.sabit?' selected':''}>${
          x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
        }</option>`)).join('');

      const subOpts = [`<option value="">— 🔗 Ana Sohbetle Aynı —</option>`]
        .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===r.subagent_sabit?' selected':''}>${
          x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
        }</option>`)).join('');

      const yas = r.yas_sn == null ? '—'
        : r.yas_sn < 90 ? '<span class="ok">şimdi</span>'
        : r.yas_sn < 3600 ? Math.round(r.yas_sn/60) + ' dk önce'
        : Math.round(r.yas_sn/3600) + ' sa önce';

      const etkinBadge = r.etkin === 'gateway'
        ? '<span class="badge badge-warn">🏢 gateway</span>'
        : r.etkin === 'abonelik'
        ? '<span class="badge badge-ok">🟢 abonelik</span>'
        : r.etkin ? `<span class="badge badge-purple">${esc(r.etkin)}</span>` : `<span class="dim">varsayılan (${esc(defRoute)})</span>`;

      const idCell = `<div><b>💬 ${esc(r.title || r.kisa)}</b>${r.group ? ` <span class="badge badge-dim">${esc(r.group)}</span>` : ''}<br><span class="mono dim" style="font-size:10.5px">${esc(r.kisa)}</span></div>`;

      const quickBtns = `
        <div class="btn-group">
          <button class="sm ${r.sabit==='abonelik'?'primary':''}" onclick="pinSessionDirect('${esc(r.id)}', 'abonelik')">🟢</button>
          <button class="sm ${r.sabit==='gateway'?'primary':''}" onclick="pinSessionDirect('${esc(r.id)}', 'gateway')">🏢</button>
          ${r.sabit ? `<button class="sm danger" onclick="pinSessionDirect('${esc(r.id)}', '')" title="Sabitlemeyi kaldır">↺</button>` : ''}
        </div>
      `;

      return [
        idCell,
        esc(r.proje || '—'),
        N(r.istek),
        r.modeller && r.modeller.length ? `<span class="badge badge-dim">${esc(r.modeller[0])}</span>` : '—',
        etkinBadge + (r.kaynak ? ` <small class="dim">(${r.kaynak})</small>` : ''),
        `<select data-sub-sid="${esc(r.id)}">${subOpts}</select>`,
        yas,
        `<select data-sid="${esc(r.id)}">${opts}</select>`,
        quickBtns
      ];
    });
    sWrap.innerHTML = renderSimpleTable(
      ['Sohbet Adı / ID', 'Proje', 'İstek', 'Model', 'Etkin Rota', 'Alt-Ajan Rotası', 'Son Görülme', 'Sabitleme', 'Hızlı'], sRows);
  }

  // --- C. Render Advanced Folder Pins Table ---
  const pFilter = (document.getElementById('project-search')?.value || '').toLowerCase();
  const allProjs = Array.from(new Set(
    (d.tum_projeler || []).concat(ses.map(r=>r.proje).filter(Boolean)).concat(Object.keys(pk))
  )).sort((a,b)=>a.localeCompare(b));

  const filteredProjs = allProjs.filter(p => !pFilter || p.toLowerCase().includes(pFilter));
  const pCountLbl = document.getElementById('project-count-lbl');
  if(pCountLbl) pCountLbl.textContent = `${filteredProjs.length} / ${allProjs.length} proje`;

  const pWrap = document.getElementById('project-pins-wrap');
  if(pWrap){
    if(!filteredProjs.length){
      pWrap.innerHTML = '<div class="card empty">Eşleşen proje bulunamadı.</div>';
    } else {
      const pRows = filteredProjs.map(p => {
        const cur = pk[p.toLowerCase()] || '';
        const opts = [`<option value="">— Varsayılan Mod (${esc(defRoute)}) —</option>`]
          .concat(rotalar.map(x => `<option value="${esc(x.ad)}"${x.ad===cur?' selected':''}>${
            x.ad==='gateway' ? '🏢 gateway' : x.ad==='abonelik' ? '🟢 abonelik' : esc(x.ad)
          }</option>`)).join('');

        const badge = cur === 'gateway'
          ? '<span class="badge badge-warn">🏢 gateway</span>'
          : cur === 'abonelik'
          ? '<span class="badge badge-ok">🟢 abonelik</span>'
          : cur
          ? `<span class="badge badge-purple">${esc(cur)}</span>`
          : `<span class="badge badge-dim">varsayılan (${esc(defRoute)})</span>`;

        const quickBtns = `
          <div class="btn-group">
            <button class="sm ${cur==='abonelik'?'primary':''}" onclick="pinProjectDirect('${esc(p)}', 'abonelik')">🟢 Abonelik</button>
            <button class="sm ${cur==='gateway'?'primary':''}" onclick="pinProjectDirect('${esc(p)}', 'gateway')">🏢 Gateway</button>
            ${cur ? `<button class="sm danger" onclick="pinProjectDirect('${esc(p)}', '')" title="Varsayılana sıfırla">↺</button>` : ''}
          </div>
        `;

        return [
          `<b>${esc(p)}</b>`,
          badge,
          `<select data-proje="${esc(p)}">${opts}</select>`,
          quickBtns
        ];
      });
      pWrap.innerHTML = renderSimpleTable(['Proje Klasörü', 'Geçerli Rota', 'Kural Seçimi', 'Hızlı Geçiş'], pRows);
    }
  }

  // --- D. Bind Dropdown Events ---
  document.querySelectorAll('select[data-group]').forEach(el => {
    el.onchange = async () => {
      el.disabled = true;
      try{
        await fetch('/__bayqus/group-pin', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({group: el.dataset.group, route: el.value})
        });
        tick(true);
      } finally { el.disabled = false; }
    };
  });

  document.querySelectorAll('select[data-group-sub]').forEach(el => {
    el.onchange = async () => {
      el.disabled = true;
      try{
        await fetch('/__bayqus/group-subagent-pin', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({group: el.dataset.groupSub, route: el.value})
        });
        tick(true);
      } finally { el.disabled = false; }
    };
  });

  document.querySelectorAll('select[data-sid]').forEach(el => {
    el.onchange = async () => {
      el.disabled = true;
      try{
        await fetch('/__bayqus/pin', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({session: el.dataset.sid, route: el.value})
        });
        tick(true);
      } finally { el.disabled = false; }
    };
  });

  document.querySelectorAll('select[data-sub-sid]').forEach(el => {
    el.onchange = async () => {
      el.disabled = true;
      try{
        await fetch('/__bayqus/subagent-pin', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({session: el.dataset.subSid, route: el.value})
        });
        tick(true);
      } finally { el.disabled = false; }
    };
  });

  document.querySelectorAll('select[data-proje]').forEach(el => {
    el.onchange = async () => {
      el.disabled = true;
      try{
        await fetch('/__bayqus/proje', {
          method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({project: el.dataset.proje, route: el.value})
        });
        tick(true);
      } finally { el.disabled = false; }
    };
  });
}

async function pinGroupDirect(group, route){
  try{
    await fetch('/__bayqus/group-pin', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group, route})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

async function pinGroupSubDirect(group, route){
  try{
    await fetch('/__bayqus/group-subagent-pin', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group, route})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

async function toggleMcpServer(group, server, disabled){
  try{
    await fetch('/__bayqus/mcp-toggle', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group, server, disabled})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

async function applyMcpPreset(group, preset){
  try{
    await fetch('/__bayqus/mcp-preset', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({group, preset})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

async function pinSessionDirect(sid, route){
  try{
    await fetch('/__bayqus/pin', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({session: sid, route})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

async function pinProjectDirect(proje, route){
  try{
    await fetch('/__bayqus/proje', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({project: proje, route})
    });
    tick(true);
  }catch(e){ alert(e.message); }
}

document.getElementById('project-search')?.addEventListener('input', () => {
  if(LATEST_DATA) renderSessionsTab(LATEST_DATA, LATEST_DATA.default_route || 'abonelik');
});

// 2. TRAFFIC LOG TAB
function renderTrafficTable(records){
  const tbody = document.getElementById('traffic-rows');
  const search = (document.getElementById('traffic-search').value||'').toLowerCase();
  const statusFilter = document.getElementById('traffic-filter-status').value;
  const agentFilter = document.getElementById('traffic-filter-agent')?.value || '';
  const modelFilter = document.getElementById('traffic-filter-model').value;
  const routeFilter = document.getElementById('traffic-filter-route').value;

  // Populate filter dropdowns
  const models = Array.from(new Set(records.map(r=>r.model).filter(Boolean)));
  const routes = Array.from(new Set(records.map(r=>r.route).filter(Boolean)));
  populateSelect('traffic-filter-model', models, modelFilter);
  populateSelect('traffic-filter-route', routes, routeFilter);

  const filtered = records.filter(r => {
    if(statusFilter === 'ok' && r.status !== 200) return false;
    if(statusFilter === 'err' && (!r.status || r.status < 400)) return false;
    if(statusFilter === 'mock' && !r.mock) return false;
    if(agentFilter === 'sub' && !r.agent) return false;
    if(agentFilter === 'main' && r.agent) return false;
    if(modelFilter && r.model !== modelFilter) return false;
    if(routeFilter && r.route !== routeFilter) return false;
    if(search){
      const text = `${r.model} ${r.route} ${r.upstream} ${r.error||''} ${r.session||''} ${r.agent||''}`.toLowerCase();
      if(!text.includes(search)) return false;
    }
    return true;
  });

  document.getElementById('traffic-count-label').textContent = `${filtered.length} / ${records.length} istek`;

  if(!filtered.length){
    tbody.innerHTML = '<tr><td colspan="14" class="empty">Eşleşen istek bulunamadı.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map((r, idx) => {
    const isErr = r.status && r.status >= 400;
    const isSub = !!r.agent;
    const statusBadge = r.mock
      ? '<span class="badge badge-warn">MOCK</span>'
      : isErr
      ? `<span class="badge badge-bad">${r.status || 'HATA'}</span>`
      : `<span class="badge badge-ok">200 OK</span>`;

    const typeBadge = isSub
      ? `<span class="badge badge-purple" title="Alt-Ajan ID: ${esc(r.agent)}">🤖 Alt-Ajan</span>`
      : `<span class="badge badge-dim">👤 Ana</span>`;

    const hitCls = r.hit > 80 ? 'ok' : r.hit > 40 ? 'warn' : 'bad';
    const hitBadge = r.hit != null ? `<span class="${hitCls}">${r.hit}%</span>` : '—';
    const pruneBadge = r.prune
      ? `<span class="badge badge-ok">Kesim ${r.cutoff||'—'} · ${N(r.saved)}B</span>`
      : '—';

    const costBadge = r.mock ? '—'
      : r.kova === 'usd_abonelik' ? `<span class="acc">${USD4(r.usd)}</span>`
      : r.kova === 'usd_bilinmiyor' ? `<span class="warn">${USD4(r.usd)}</span>`
      : USD4(r.usd);

    return `<tr class="clickable ${isErr?'err-row':''} ${isSub?'subagent-row':''}" onclick="inspectRecord(${idx})">
      <td class="mono">${esc(r.ts)}</td>
      <td>${statusBadge}</td>
      <td><b>${esc(r.model)}</b>${r.model_sent && r.model_sent!==r.model ? `<br><small class="dim">↳ ${esc(r.model_sent)}</small>` : ''}</td>
      <td>${typeBadge}</td>
      <td><span class="badge ${r.route==='gateway'?'badge-warn':r.route==='abonelik'?'badge-ok':'badge-dim'}">${esc(r.route||'—')}</span></td>
      <td class="mono" style="font-size:11px">${esc(r.upstream||'—')}</td>
      <td>${N(r.ms)} ms</td>
      <td>${N(r.messages)}</td>
      <td>${N(r.context)}</td>
      <td>${N(r.output)}</td>
      <td>${hitBadge}</td>
      <td>${pruneBadge}</td>
      <td>${costBadge}</td>
      <td><button class="sm" onclick="event.stopPropagation();inspectRecord(${idx})">🔍</button></td>
    </tr>`;
  }).join('');
}

function populateSelect(id, items, currentVal){
  const sel = document.getElementById(id);
  if(!sel) return;
  const first = sel.options[0].text;
  sel.innerHTML = `<option value="">${first}</option>` +
    items.map(it => `<option value="${esc(it)}"${it===currentVal?' selected':''}>${esc(it)}</option>`).join('');
}

document.getElementById('traffic-search')?.addEventListener('input', () => {
  if(LATEST_DATA) renderTrafficTable(LATEST_DATA.son || []);
});
['traffic-filter-status', 'traffic-filter-agent', 'traffic-filter-model', 'traffic-filter-route'].forEach(id => {
  document.getElementById(id)?.addEventListener('change', () => {
    if(LATEST_DATA) renderTrafficTable(LATEST_DATA.son || []);
  });
});

// INSPECT MODAL
function inspectRecord(idx){
  if(!LATEST_DATA || !LATEST_DATA.son || !LATEST_DATA.son[idx]) return;
  const r = LATEST_DATA.son[idx];
  const modal = document.getElementById('inspector-modal');
  const title = document.getElementById('insp-title');
  const body = document.getElementById('insp-content');

  const isErr = r.status && r.status >= 400;
  const isSub = !!r.agent;
  title.innerHTML = `İstek Detayı · ${esc(r.model)} ${isSub?'[🤖 Alt-Ajan]':''} (${r.status || 'Hata'})`;

  let h = '';
  if(isErr || r.error){
    h += `<div style="background:var(--bad-bg);border:1px solid var(--bad);border-radius:var(--radius);padding:14px;margin-bottom:16px">
      <div style="font-weight:700;color:var(--bad);margin-bottom:4px">⚠️ Hata Meydana Geldi (${r.status || 502})</div>
      <div class="mono" style="font-size:12px;color:var(--bad);word-break:break-all">${esc(r.error || 'İstek başarısız oldu')}</div>
      <div style="font-size:12px;margin-top:8px;color:var(--ink)">
        Hedef Upstream: <b>${esc(r.upstream)}</b><br>
        DNS / Ağ Hatası ise VPN bağlantınızı veya proje/rota ayarlarını kontrol edin.
      </div>
    </div>`;
  }

  // Quick Action Buttons
  const foundProj = (LATEST_DATA?.oturumlar || []).find(s => s.id === r.session)?.proje || '';
  h += `<div class="card" style="margin-bottom:16px;background:var(--bg);display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <span style="font-size:11px;font-weight:600;color:var(--dim)">HIZLI YÖNLENDİRME:</span>
    ${r.session ? `
      <button class="sm" onclick="quickPinSession('${esc(r.session)}', 'gateway')">🏢 Bu Sohbeti Gateway'e Sabitle</button>
      <button class="sm" onclick="quickPinSession('${esc(r.session)}', 'abonelik')">🟢 Bu Sohbeti Aboneliğe Sabitle</button>
      <button class="sm" onclick="quickPinSession('${esc(r.session)}', '')">❌ Sabitlemeyi Kaldır</button>
    ` : ''}
    ${foundProj ? `
      <button class="sm primary" onclick="quickPinProject('${esc(foundProj)}', 'gateway')">🏢 Projeyi (${esc(foundProj.split('/').pop())}) Gateway'e Bağla</button>
      <button class="sm primary" onclick="quickPinProject('${esc(foundProj)}', 'abonelik')">🟢 Projeyi (${esc(foundProj.split('/').pop())}) Aboneliğe Bağla</button>
    ` : ''}
  </div>`;

  h += `<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(130px,1fr));margin-bottom:16px">
    <div class="card"><div class="k">Durum</div><div class="v ${isErr?'bad':'ok'}">${r.status||'—'}</div></div>
    <div class="card"><div class="k">Gecikme</div><div class="v">${N(r.ms)} ms</div></div>
    <div class="card"><div class="k">Toplam Bağlam</div><div class="v">${N(r.context)}</div><div class="n">token</div></div>
    <div class="card"><div class="k">Cache İsabeti</div><div class="v ${r.hit>70?'ok':'warn'}">${r.hit!=null?r.hit+'%':'—'}</div></div>
    <div class="card"><div class="k">Maliyet</div><div class="v acc">${USD4(r.usd)}</div><div class="n">${r.kova||''}</div></div>
  </div>`;

  h += `<h2>Token Dökümü</h2>
  <div class="wrap" style="margin-bottom:16px">
    <table>
      <thead><tr><th>Girdi (Prompt)</th><th>Çıktı (Output)</th><th>Cache Okunan</th><th>Cache Yazılan</th><th>Tasarruf (Budama)</th></tr></thead>
      <tbody><tr>
        <td>${N(r.input)} token</td>
        <td>${N(r.output)} token</td>
        <td class="ok">${N(r.cache_read)} token</td>
        <td>${N(r.cache_creation)} token</td>
        <td class="acc">${r.saved ? N(r.saved) + ' B (~' + N(Math.round(r.saved/4)) + ' token)' : '—'}</td>
      </tr></tbody>
    </table>
  </div>`;

  const pr = r.prune_details || {};
  h += `<h2>Budama (Pruning) Karnesi</h2>
  <div class="card" style="margin-bottom:16px">
    <div>Budama Uygulandı mı: <b>${r.prune ? '<span class="ok">EVET</span>' : '<span class="dim">HAYIR (' + esc(pr.reason||'uygulanmadı') + ')</span>'}</b></div>
    ${r.prune ? `<div style="margin-top:6px">Kesim Noktası: <b>${pr.cutoff} / ${pr.total_messages} mesaj</b></div>
    <div style="margin-top:6px">Önek Durumu: <b>${pr.prefix_stable ? 'Kararlı (=)' : 'Yeni Önek'} (${esc(pr.prefix_hash||'')})</b></div>` : ''}
  </div>`;

  h += `<h2>Oturum ve Alt-Ajan Detayları</h2>
  <div class="card" style="margin-bottom:16px;font-size:12.5px">
    <div>Ajan Türü: <b>${isSub ? '<span class="badge badge-purple">🤖 Alt-Ajan (Sub-Agent)</span>' : '<span class="badge badge-dim">👤 Ana Oturum</span>'}</b></div>
    <div>Rota: <b>${esc(r.route)}</b></div>
    <div>Upstream: <span class="mono">${esc(r.upstream)}</span></div>
    <div>Model Gönderilen: <span class="mono">${esc(r.model_sent || r.model)}</span></div>
    <div>Oturum ID: <span class="mono">${esc(r.session || '—')}</span></div>
    ${r.agent ? `<div>Alt-Ajan ID: <span class="mono">${esc(r.agent)}</span></div>` : ''}
    ${foundProj ? `<div>Proje Klasörü: <b>${esc(foundProj)}</b></div>` : ''}
    <div>Mesaj Sayısı: <b>${N(r.messages)}</b> · Araç Sayısı: <b>${N(r.tools)}</b></div>
    <div>İstek Boyutu: <b>${N(r.req_bytes)} B</b> · Yanıt Boyutu: <b>${N(r.resp_bytes)} B</b></div>
  </div>`;

  h += `<h2>Ham Kayıt (JSON)</h2>
  <pre class="mono" style="background:var(--bg);padding:10px;border-radius:6px;overflow-x:auto;font-size:11px">${esc(JSON.stringify(r, null, 2))}</pre>`;

  body.innerHTML = h;
  openModal('inspector-modal');
}

async function quickPinSession(sid, route){
  await pinSessionDirect(sid, route);
  closeModal('inspector-modal');
}

async function quickPinProject(proje, route){
  await pinProjectDirect(proje, route);
  closeModal('inspector-modal');
}

// 3. ANALYTICS TAB
function renderAnalytics(d){
  const t = d.toplam || {};
  const kpis = document.getElementById('analytics-kpis');
  const hit = t.context ? (t.cache_read / t.context * 100) : 0;
  const successCount = (t.istek||0) - (t.hata||0);
  const successPct = t.istek ? (successCount / t.istek * 100).toFixed(1) : 100;

  kpis.innerHTML = `
    <div class="card">
      <div class="k">Toplam İstek</div>
      <div class="v">${N(t.istek)}</div>
      <div class="n">%${successPct} başarı · ${N(t.hata||0)} hata</div>
    </div>
    <div class="card">
      <div class="k">Gerçek Harcama</div>
      <div class="v bad">${USD(t.usd_gercek)}</div>
      <div class="n">gateway / API rotaları</div>
    </div>
    <div class="card">
      <div class="k">Abonelik Değeri</div>
      <div class="v acc">${USD(t.usd_abonelik)}</div>
      <div class="n">API ile ödenseydi</div>
    </div>
    <div class="card">
      <div class="k">Cache İsabeti</div>
      <div class="v ${hit>70?'ok':hit>40?'warn':'bad'}">${hit.toFixed(1)}%</div>
      <div class="n">${N(t.cache_read)} token okundu</div>
    </div>
    <div class="card">
      <div class="k">Budama Kazancı</div>
      <div class="v ok">${N(t.bytes_saved)} B</div>
      <div class="n">~${N(Math.round((t.bytes_saved||0)/4))} token tasarrufu</div>
    </div>
    <div class="card">
      <div class="k">Ort. Yanıt Süresi</div>
      <div class="v">${t.istek ? N(Math.round(t.ms/t.istek)) : 0} ms</div>
      <div class="n">ort. bağlam ${t.istek ? N(Math.round(t.context/t.istek)) : 0} tok</div>
    </div>
  `;

  // Token Bar
  const totalTokens = (t.input||0) + (t.output||0) + (t.cache_read||0);
  if(totalTokens > 0){
    const rPct = (t.cache_read||0) / totalTokens * 100;
    const iPct = (t.input||0) / totalTokens * 100;
    const oPct = (t.output||0) / totalTokens * 100;
    document.getElementById('td-read').style.width = rPct + '%';
    document.getElementById('td-inp').style.width = iPct + '%';
    document.getElementById('td-out').style.width = oPct + '%';
    document.getElementById('td-read-lbl').textContent = `${N(t.cache_read)} (%${rPct.toFixed(1)})`;
    document.getElementById('td-inp-lbl').textContent = `${N(t.input)} (%${iPct.toFixed(1)})`;
    document.getElementById('td-out-lbl').textContent = `${N(t.output)} (%${oPct.toFixed(1)})`;
  }

  // Model Table
  const mRows = Object.entries(d.model||{}).map(([m,v]) => [
    `<b>${esc(m)}</b>`, N(v.istek), N(v.context), N(v.output),
    v.context ? (v.cache_read/v.context*100).toFixed(1)+'%' : '—',
    v.usd_gercek ? USD4(v.usd_gercek) : '—',
    v.usd_abonelik ? `<span class="acc">${USD4(v.usd_abonelik)}</span>` : '—',
  ]);
  document.getElementById('model-table-wrap').innerHTML = renderSimpleTable(
    ['Model', 'İstek', 'Bağlam Token', 'Çıktı Token', 'Cache İsabet', 'Gerçek ($)', 'Abonelik Eşd. ($)'], mRows);

  // Route Table
  const rRows = Object.entries(d.rota||{}).map(([r,v]) => [
    `<b>${esc(r)}</b>`, N(v.istek), N(v.context), N(v.bytes_saved)+' B',
    v.usd_gercek ? USD4(v.usd_gercek) : '—',
    v.usd_abonelik ? `<span class="acc">${USD4(v.usd_abonelik)}</span>` : '—',
  ]);
  document.getElementById('route-table-wrap').innerHTML = renderSimpleTable(
    ['Rota', 'İstek', 'Bağlam Token', 'Budanan Bayt', 'Gerçek ($)', 'Abonelik Eşd. ($)'], rRows);

  // Day Table
  const maxDay = Math.max(1, ...Object.values(d.gun||{}).map(v=>v.context||0));
  const dRows = Object.entries(d.gun||{}).map(([g,v]) => [
    esc(g), N(v.istek),
    `${N(v.context)} <div class="bar"><i style="width:${(v.context/maxDay*100)}%"></i></div>`,
    USD4(v.usd_gercek||0), `<span class="acc">${USD4(v.usd_abonelik||0)}</span>`
  ]);
  document.getElementById('day-table-wrap').innerHTML = renderSimpleTable(
    ['Gün', 'İstek', 'Bağlam Token', 'Gerçek ($)', 'Abonelik Eşd. ($)'], dRows);
}

function renderSimpleTable(cols, rows){
  if(!rows.length) return '<div class="empty">Veri yok</div>';
  return `<table><thead><tr>${cols.map(c=>`<th>${c}</th>`).join('')}</tr></thead><tbody>${
    rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

// 4. ROUTES TAB
function renderRoutesTab(routesCfg, liveRoutes, defRoute){
  const list = document.getElementById('routes-list');
  const routes = routesCfg.routes || [];
  const def = routesCfg.default || {};

  if(!routes.length){
    list.innerHTML = '<div class="card empty">Tanımlı özel rota yok. Tüm trafik varsayılan rotaya gider.</div>';
  } else {
    list.innerHTML = routes.map((r, i) => {
      const isEn = r.enabled !== false;
      const patterns = (r.model_contains || []).map(p=>`<span class="badge badge-purple">${esc(p)}</span>`).join(' ');
      const authStr = typeof r.auth === 'string' ? r.auth : (r.auth?.header ? `${r.auth.header} (${r.auth.env||'file'})` : 'özel');

      return `<div class="route-card ${isEn?'':'disabled'}">
        <div class="route-head">
          <div class="route-name">
            <label class="switch">
              <input type="checkbox" ${isEn?'checked':''} onchange="toggleRoute('${esc(r.name)}', this.checked)">
              <span class="slider"></span>
            </label>
            <span>${esc(r.name)}</span>
            <span class="badge ${isEn?'badge-ok':'badge-dim'}">${isEn?'AKTİF':'PASİF'}</span>
            ${r.prune===false ? '<span class="badge badge-warn">Budama Kapalı</span>' : '<span class="badge badge-dim">Budama Açık</span>'}
            ${r.name === defRoute ? '<span class="badge badge-ok">ŞU ANKİ VARSAYILAN MOD</span>' : ''}
          </div>
          <div>
            <button class="sm" onclick="editRoute(${i})">Düzenle ✏️</button>
            <button class="sm danger" onclick="deleteRoute('${esc(r.name)}')">Sil 🗑️</button>
          </div>
        </div>
        <div class="route-details">
          <span><b>Upstream:</b> <span class="mono">${esc(r.upstream)}</span></span>
          <span><b>Modeller:</b> ${patterns || '<span class="dim">herhangi biri (proje/oturum kuralı)</span>'}</span>
          <span><b>Kimlik:</b> <span class="badge badge-dim">${esc(authStr)}</span></span>
          ${r.model_rewrite ? `<span><b>Yeniden Yaz:</b> <span class="badge badge-blue">${esc(r.model_rewrite)}</span></span>` : ''}
        </div>
      </div>`;
    }).join('');
  }

  // Default Route Card
  document.getElementById('default-route-card').innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-weight:700;font-size:15px;margin-bottom:4px">
          Aktif Varsayılan Mod: <b class="${defRoute==='gateway'?'warn':'ok'}">${esc(defRoute)}</b>
        </div>
        <div class="dim" style="font-size:12px">Hiçbir oturum veya proje kuralı bulunmadığında istekler otomatik olarak bu rotaya gider.</div>
      </div>
      <div class="btn-group">
        <button class="sm ${defRoute==='abonelik'?'primary':''}" onclick="setDefaultRoute('abonelik')">🟢 Aboneliği Varsayılan Yap</button>
        <button class="sm ${defRoute==='gateway'?'primary':''}" onclick="setDefaultRoute('gateway')">🏢 Gateway'i Varsayılan Yap</button>
      </div>
    </div>
    <div style="display:flex;gap:16px;margin-top:12px;font-size:12px;flex-wrap:wrap">
      <span><b>Upstream:</b> <span class="mono">${esc(def.upstream||'—')}</span></span>
      <span><b>Kimlik:</b> <span class="badge badge-dim">${esc(typeof def.auth==='string'?def.auth:'özelleştirilmiş')}</span></span>
      <span><b>Budama:</b> ${def.prune!==false?'Açık':'Kapalı'}</span>
    </div>
  `;
}

// Route actions
async function toggleRoute(name, enabled){
  try{
    const r = await fetch('/__bayqus/routes/toggle', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name, enabled})
    });
    const j = await r.json();
    if(!j.ok) alert('Hata: ' + j.mesaj);
    tick(true);
  }catch(e){ alert('Bağlantı hatası: ' + e.message); }
}

async function deleteRoute(name){
  if(!confirm(`"${name}" rotasını silmek istediğinize emin misiniz?`)) return;
  try{
    const r = await fetch('/__bayqus/routes/delete', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({name})
    });
    const j = await r.json();
    if(!j.ok) alert('Hata: ' + j.mesaj);
    tick(true);
  }catch(e){ alert('Bağlantı hatası: ' + e.message); }
}

function openNewRouteModal(){
  document.getElementById('route-modal-title').textContent = 'Yeni Rota Ekle';
  document.getElementById('rf-name').value = '';
  document.getElementById('rf-name').disabled = false;
  document.getElementById('rf-upstream').value = 'https://';
  document.getElementById('rf-contains').value = '';
  document.getElementById('rf-rewrite').value = '';
  document.getElementById('rf-auth-type').value = 'passthrough';
  document.getElementById('rf-enabled').checked = true;
  document.getElementById('rf-prune').checked = true;
  toggleAuthFields();
  openModal('route-modal');
}

function editRoute(idx){
  if(!LATEST_DATA || !LATEST_DATA.routes_config || !LATEST_DATA.routes_config.routes) return;
  const r = LATEST_DATA.routes_config.routes[idx];
  document.getElementById('route-modal-title').textContent = 'Rotayı Düzenle: ' + r.name;
  document.getElementById('rf-name').value = r.name || '';
  document.getElementById('rf-name').disabled = true;
  document.getElementById('rf-upstream').value = r.upstream || '';
  document.getElementById('rf-contains').value = (r.model_contains || []).join(', ');
  document.getElementById('rf-rewrite').value = r.model_rewrite || '';
  document.getElementById('rf-enabled').checked = r.enabled !== false;
  document.getElementById('rf-prune').checked = r.prune !== false;

  if(typeof r.auth === 'string'){
    document.getElementById('rf-auth-type').value = r.auth;
  } else if(r.auth?.file){
    document.getElementById('rf-auth-type').value = 'file';
    document.getElementById('rf-auth-file').value = r.auth.file || '';
    document.getElementById('rf-auth-key').value = r.auth.json_key || '';
  } else if(r.auth?.env){
    document.getElementById('rf-auth-type').value = 'env';
    document.getElementById('rf-auth-env').value = r.auth.env || '';
  }
  toggleAuthFields();
  openModal('route-modal');
}

async function saveRouteForm(e){
  e.preventDefault();
  const name = document.getElementById('rf-name').value.trim();
  const upstream = document.getElementById('rf-upstream').value.trim();
  const containsStr = document.getElementById('rf-contains').value;
  const contains = containsStr.split(',').map(s=>s.trim()).filter(Boolean);
  const rewrite = document.getElementById('rf-rewrite').value.trim() || undefined;
  const enabled = document.getElementById('rf-enabled').checked;
  const prune = document.getElementById('rf-prune').checked;
  const authType = document.getElementById('rf-auth-type').value;

  let auth = authType;
  if(authType === 'file'){
    auth = {
      header: "Authorization", prefix: "Bearer ",
      file: document.getElementById('rf-auth-file').value.trim(),
      json_key: document.getElementById('rf-auth-key').value.trim() || "inferenceGatewayApiKey"
    };
  } else if(authType === 'env'){
    auth = {
      header: "Authorization", prefix: "Bearer ",
      env: document.getElementById('rf-auth-env').value.trim()
    };
  }

  const routeData = {
    name, enabled, upstream, model_contains: contains, auth, prune,
    ...(rewrite ? {model_rewrite: rewrite} : {})
  };

  try{
    const r = await fetch('/__bayqus/routes/save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({route: routeData})
    });
    const j = await r.json();
    if(!j.ok){
      alert('Kaydedilemedi: ' + j.mesaj);
      return;
    }
    closeModal('route-modal');
    tick(true);
  }catch(err){ alert('Hata: ' + err.message); }
}

function openJsonModal(){
  if(!LATEST_DATA || !LATEST_DATA.routes_config) return;
  document.getElementById('json-editor').value = JSON.stringify(LATEST_DATA.routes_config, null, 2);
  openModal('json-modal');
}

async function saveJsonConfig(){
  const txt = document.getElementById('json-editor').value;
  let parsed;
  try{ parsed = JSON.parse(txt); }
  catch(e){ alert('Geçersiz JSON: ' + e.message); return; }

  try{
    const r = await fetch('/__bayqus/routes/all', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({config: parsed})
    });
    const j = await r.json();
    if(!j.ok){ alert('Kaydedilemedi: ' + j.mesaj); return; }
    closeModal('json-modal');
    tick(true);
  }catch(err){ alert('Hata: ' + err.message); }
}

async function updateProxyConfig(){
  const mode = document.getElementById('config-mode').value;
  const mock = document.getElementById('config-mock').checked;
  try{
    const r = await fetch('/__bayqus/config', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({mode, mock_classifier: mock})
    });
    const j = await r.json();
    if(j.ok) tick(true);
  }catch(e){ alert('Ayar güncellenemedi: ' + e.message); }
}

// 5. SUMMARIZER & PREFIX CACHE TAB
function renderSummarizerTab(d){
  const s = d.summarizer_settings || {};
  const cs = d.cache_stats || {};
  const bf = d.bridge_files || {};
  const pend = d.pending_summaries || [];

  // KPIs
  document.getElementById('kpi-cache-entries').textContent = N(cs.entries || 0);
  document.getElementById('kpi-cache-hits').textContent = N(cs.total_hits || 0);
  document.getElementById('kpi-cache-tokens').textContent = N(cs.total_tokens_saved || 0) + ' Token';
  const kbSaved = Math.round((cs.total_bytes_saved || 0) / 1024);
  document.getElementById('kpi-cache-bytes').textContent = N(kbSaved) + ' KB Tasarruf';
  document.getElementById('kpi-agent-queue').textContent = `${bf.pending || 0} / ${bf.ready || 0}`;

  // Form values (only update if user is not actively typing)
  const keyInput = document.getElementById('sum-api-key');
  if(document.activeElement !== keyInput && keyInput){
    document.getElementById('sum-mode').value = s.summarizer_mode || 'hybrid';
    document.getElementById('sum-model').value = s.preferred_gemini_model || 'round-robin';
    document.getElementById('sum-block').value = s.block_size || '16';
    document.getElementById('sum-keep-recent').value = s.keep_recent_messages || '24';
    if(s.masked_api_key && !keyInput.dataset.edited){
      keyInput.value = s.masked_api_key;
    }
  }

  // Pending queue table
  const pWrap = document.getElementById('pending-summaries-wrap');
  if(pWrap){
    if(!pend.length){
      pWrap.innerHTML = '<div class="card empty">Şu anda özetlenmeyi bekleyen uzun oturum isteği bulunmuyor. Mesaj sayısı 20\'yi geçtiğinde burada otomatik listelenir.</div>';
    } else {
      const rows = pend.map(item => {
        return [
          `<span class="mono"><b>${esc(item.session_key)}</b></span>`,
          `<span class="mono">${esc((item.prefix_hash||'').slice(0,12))}</span>`,
          `${item.message_count || 0} mesaj`,
          `<small class="mono">${esc(item.created_at || '—')}</small>`,
          `<button class="sm primary" onclick="promptSubmitAgentSummary('${esc(item.prefix_hash)}')">Özet Teslim Et 📝</button>`
        ];
      });
      pWrap.innerHTML = renderSimpleTable(['Oturum Anahtarı', 'Prefix Hash', 'Mesaj Sayısı', 'İstek Zamanı', 'İşlem'], rows);
    }
  }
}

document.getElementById('sum-api-key')?.addEventListener('input', () => {
  document.getElementById('sum-api-key').dataset.edited = 'true';
});

function toggleApiKeyVisibility(){
  const el = document.getElementById('sum-api-key');
  if(el) el.type = el.type === 'password' ? 'text' : 'password';
}

async function saveSummarizerSettings(e){
  e.preventDefault();
  const mode = document.getElementById('sum-mode').value;
  const model = document.getElementById('sum-model').value;
  const block = document.getElementById('sum-block').value;
  const keep = document.getElementById('sum-keep-recent').value;
  const apiKeyInput = document.getElementById('sum-api-key');
  
  const payload = {
    summarizer_mode: mode,
    enable_ai_summarizer: mode !== 'deterministic',
    preferred_gemini_model: model,
    block_size: block,
    keep_recent_messages: keep
  };

  if(apiKeyInput.dataset.edited && apiKeyInput.value && !apiKeyInput.value.includes('...')){
    payload.ai_studio_api_key = apiKeyInput.value.trim();
  }

  try{
    const r = await fetch('/__bayqus/summarizer/settings', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    alert(j.mesaj || 'Ayarlar kaydedildi!');
    apiKeyInput.dataset.edited = '';
    tick(true);
  }catch(err){ alert('Hata: ' + err.message); }
}

async function clearPrefixCache(){
  if(!confirm('Tüm prefix önbelleği temizlensin mi? (Oturumlar bir sonraki turda yeniden taze özetlenecek)')) return;
  try{
    const r = await fetch('/__bayqus/summarizer/clear-cache', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({})
    });
    const j = await r.json();
    alert(j.mesaj || 'Önbellek temizlendi!');
    tick(true);
  }catch(err){ alert('Hata: ' + err.message); }
}

async function testGeminiApi(){
  const keyInput = document.getElementById('sum-api-key');
  const apiKey = (keyInput.dataset.edited && keyInput.value && !keyInput.value.includes('...')) ? keyInput.value.trim() : '';
  const model = document.getElementById('sum-model').value;

  try{
    const r = await fetch('/__bayqus/summarizer/test-gemini', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({api_key: apiKey, model})
    });
    const j = await r.json();
    alert(j.mesaj + (j.sample ? '\n\nÖrnek Çıktı:\n' + j.sample : ''));
  }catch(err){ alert('Hata: ' + err.message); }
}

async function promptSubmitAgentSummary(prefixHash){
  const text = prompt(`Prefix [${prefixHash.slice(0,8)}] için Antigravity Ajan Özeti girin:`);
  if(!text || !text.trim()) return;
  try{
    const r = await fetch('/__bayqus/summarizer/submit-summary', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({prefix_hash: prefixHash, summary_text: text.trim(), agent_name: 'antigravity_agent'})
    });
    const j = await r.json();
    alert(j.mesaj || 'Özet kaydedildi!');
    tick(true);
  }catch(err){ alert('Hata: ' + err.message); }
}

// === İSTEK GEÇMİŞİ & MESAJ İÇERİKLERİ (SON 5000) ===
let CURRENT_HIST_OFFSET = 0;
const HIST_PAGE_SIZE = 30;

async function loadHistory(offset = 0) {
  CURRENT_HIST_OFFSET = offset;
  const tbody = document.getElementById('hist-tbody');
  tbody.innerHTML = '<tr><td colspan="11" class="empty">İstek geçmişi yükleniyor...</td></tr>';
  const q = encodeURIComponent(document.getElementById('hist-search')?.value || '');
  try {
    const url = `/__bayqus/history?limit=${HIST_PAGE_SIZE}&offset=${offset}` + (q ? `&q=${q}` : '');
    const res = await fetch(url, {cache: 'no-store'});
    const data = await res.json();
    const total = data.total || 0;
    const items = data.items || [];

    document.getElementById('hist-total-badge').textContent = `Toplam: ${N(total)}`;
    document.getElementById('hist-page-info').textContent = total === 0 ? 'Kayıt yok' :
      `${offset + 1} - ${Math.min(offset + items.length, total)} / ${N(total)} gösteriliyor`;
    document.getElementById('hist-prev-btn').disabled = offset <= 0;
    document.getElementById('hist-next-btn').disabled = offset + items.length >= total;

    if (items.length === 0) {
      tbody.innerHTML = '<tr><td colspan="11" class="empty">Kayıtlı istek bulunamadı.</td></tr>';
      return;
    }

    tbody.innerHTML = items.map(it => {
      const u = it.usage || {};
      const inp = u.input_tokens || 0;
      const out = u.output_tokens || 0;
      const cr = u.cache_read_input_tokens || 0;
      const ts = (it.ts || '').slice(0, 19).replace('T', ' ');
      const dur = `${it.duration_ms}ms`;
      const pruneBadge = it.prune_applied ? ' <span class="badge badge-warn" title="Delta Budama Uygulandı">Budandı</span>' : '';
      const statusBadge = it.status_code === 200 ?
        '<span class="badge badge-ok">200 OK</span>' :
        `<span class="badge badge-bad">${it.status_code}</span>`;
      const sid = (it.session_id || '').slice(0, 10);
      const reqB = (it.req_bytes || 0) > 1024 ? `${Math.round(it.req_bytes / 1024)} KB` : `${it.req_bytes || 0} B`;

      return `
        <tr class="clickable" onclick="openHistoryDetail(${it.id})">
          <td class="mono"><strong>#${it.id}</strong></td>
          <td class="mono" style="font-size:11px">${esc(ts)}</td>
          <td>${statusBadge}</td>
          <td class="mono">${esc(dur)}</td>
          <td style="text-align:left"><span class="badge badge-dim mono">${esc(it.model || '-')}</span>${pruneBadge}</td>
          <td class="mono">${N(inp)}</td>
          <td class="mono">${N(out)}</td>
          <td class="mono ${cr > 0 ? 'ok' : 'dim'}">${cr > 0 ? N(cr) : '-'}</td>
          <td class="mono dim">${esc(reqB)}</td>
          <td class="mono dim" title="${esc(it.session_id)}">${esc(sid || '-')}</td>
          <td><button class="sm primary" onclick="event.stopPropagation();openHistoryDetail(${it.id})">🔍 İncele</button></td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="11" class="empty bad">Yükleme hatası: ${esc(err.message)}</td></tr>`;
  }
}

function prevHistoryPage() {
  if (CURRENT_HIST_OFFSET >= HIST_PAGE_SIZE) {
    loadHistory(CURRENT_HIST_OFFSET - HIST_PAGE_SIZE);
  }
}

function nextHistoryPage() {
  loadHistory(CURRENT_HIST_OFFSET + HIST_PAGE_SIZE);
}

async function openHistoryDetail(id) {
  openModal('history-modal');
  const body = document.getElementById('hist-modal-body');
  document.getElementById('hist-modal-title').textContent = `İstek & Yanıt Detayı (#${id})`;
  body.innerHTML = '<div class="empty">Yükleniyor...</div>';
  try {
    const res = await fetch(`/__bayqus/history?id=${id}`);
    const req = await res.json();
    if (!req || req.error) {
      body.innerHTML = `<div class="empty bad">İstek bulunamadı: ${esc(req?.error || '')}</div>`;
      return;
    }

    const u = req.usage || {};
    let html = `
      <div class="grid" style="margin-bottom:14px;grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">
        <div class="card"><div class="k">ZAMAN</div><div class="v" style="font-size:13px">${esc(req.ts?.slice(0,19).replace('T',' '))}</div></div>
        <div class="card"><div class="k">MODEL</div><div class="v" style="font-size:13px">${esc(req.model || '-')}</div></div>
        <div class="card"><div class="k">DURUM / SÜRE</div><div class="v" style="font-size:13px">${req.status_code} (${req.duration_ms}ms)</div></div>
        <div class="card"><div class="k">GİRDİ / ÇIKTI</div><div class="v" style="font-size:13px">${N(u.input_tokens||0)} / ${N(u.output_tokens||0)}</div></div>
        <div class="card"><div class="k">CACHE OKU / YAZ</div><div class="v" style="font-size:13px">${N(u.cache_read_input_tokens||0)} / ${N(u.cache_creation_input_tokens||0)}</div></div>
      </div>
    `;

    if (req.prune_applied) {
      const p = req.prune_info || {};
      html += `
        <div style="background:var(--warn-bg);border:1px solid var(--warn);padding:8px 12px;border-radius:6px;margin-bottom:12px;font-size:12px">
          <strong>⚡ Budama Uygulandı:</strong> Kesim Sınırı: ${p.cutoff || '-'}, Sebep: ${p.reason || 'delta_ledger'}
        </div>
      `;
    }

    if (req.system_prompt) {
      html += `
        <h3 style="font-size:13px;margin:12px 0 6px">📋 Sistem Yönergesi (${N(req.system_prompt.length)} karakter)</h3>
        <pre style="background:var(--bg);padding:10px;border-radius:6px;max-height:180px;overflow-y:auto;white-space:pre-wrap;font-size:11.5px;border:1px solid var(--line)">${esc(req.system_prompt)}</pre>
      `;
    }

    const msgs = req.messages;
    html += `<h3 style="font-size:13px;margin:16px 0 6px">💬 Giden Mesajlar (${Array.isArray(msgs) ? msgs.length : 0} Adet)</h3>`;
    if (Array.isArray(msgs)) {
      html += msgs.map((m, idx) => {
        const role = (m.role || 'unknown').toUpperCase();
        const roleBadge = role === 'USER' ? 'badge-blue' : (role === 'ASSISTANT' ? 'badge-purple' : 'badge-dim');
        let contentHtml = '';
        if (typeof m.content === 'string') {
          contentHtml = `<pre style="white-space:pre-wrap;margin:4px 0 0;font-size:12px">${esc(m.content)}</pre>`;
        } else if (Array.isArray(m.content)) {
          contentHtml = m.content.map((b, bIdx) => {
            if (b.type === 'text') {
              return `<div style="margin:3px 0"><span class="badge badge-dim">text</span> <pre style="white-space:pre-wrap;margin:2px 0 0;font-size:12px">${esc(b.text||'')}</pre></div>`;
            } else if (b.type === 'tool_use') {
              return `<div style="margin:4px 0;background:rgba(217,119,6,0.06);padding:6px;border-radius:4px;border:1px solid rgba(217,119,6,0.2)">
                <span class="badge badge-warn">tool_use: ${esc(b.name)}</span> (id: ${esc(b.id||'')})
                <pre style="white-space:pre-wrap;margin:2px 0 0;font-size:11.5px">${esc(JSON.stringify(b.input||{}, null, 2))}</pre>
              </div>`;
            } else if (b.type === 'tool_result') {
              const resText = typeof b.content === 'string' ? b.content : JSON.stringify(b.content, null, 2);
              return `<div style="margin:4px 0;background:rgba(22,163,74,0.06);padding:6px;border-radius:4px;border:1px solid rgba(22,163,74,0.2)">
                <span class="badge badge-ok">tool_result</span> (id: ${esc(b.tool_use_id||'')})
                <pre style="white-space:pre-wrap;margin:2px 0 0;font-size:11.5px;max-height:220px;overflow-y:auto">${esc(resText||'')}</pre>
              </div>`;
            }
            return `<pre style="font-size:11px">${esc(JSON.stringify(b))}</pre>`;
          }).join('');
        }
        return `
          <div style="background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:10px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span class="badge ${roleBadge}">#${idx+1} ${role}</span>
            </div>
            ${contentHtml}
          </div>
        `;
      }).join('');
    }

    const resp = req.response;
    html += `<h3 style="font-size:13px;margin:16px 0 6px">🤖 Gelen Model Yanıtı</h3>`;
    if (Array.isArray(resp)) {
      html += resp.map((b, bIdx) => {
        if (b.type === 'text') {
          return `
            <div style="background:var(--ok-bg);border:1px solid var(--ok);border-radius:6px;padding:10px;margin-bottom:8px">
              <span class="badge badge-ok">text</span>
              <pre style="white-space:pre-wrap;margin:4px 0 0;font-size:12.5px">${esc(b.text || '')}</pre>
            </div>
          `;
        } else if (b.type === 'tool_use') {
          return `
            <div style="background:var(--warn-bg);border:1px solid var(--warn);border-radius:6px;padding:10px;margin-bottom:8px">
              <span class="badge badge-warn">tool_use: ${esc(b.name)}</span> (id: ${esc(b.id||'')})
              <pre style="white-space:pre-wrap;margin:4px 0 0;font-size:12px">${esc(JSON.stringify(b.input || {}, null, 2))}</pre>
            </div>
          `;
        } else if (b.type === 'thinking') {
          return `
            <div style="background:var(--purple-bg);border:1px solid var(--purple);border-radius:6px;padding:10px;margin-bottom:8px">
              <span class="badge badge-purple">thinking</span>
              <pre style="white-space:pre-wrap;margin:4px 0 0;font-size:11.5px;max-height:180px;overflow-y:auto">${esc(b.thinking || '')}</pre>
            </div>
          `;
        } else if (b.type === 'error') {
          return `
            <div style="background:var(--bad-bg);border:1px solid var(--bad);border-radius:6px;padding:10px;margin-bottom:8px">
              <span class="badge badge-bad">Hata</span>
              <pre style="white-space:pre-wrap;margin:4px 0 0;font-size:12px">${esc(JSON.stringify(b, null, 2))}</pre>
            </div>
          `;
        }
        return `<pre style="background:var(--bg);padding:8px;border-radius:6px;font-size:11.5px">${esc(JSON.stringify(b, null, 2))}</pre>`;
      }).join('');
    } else if (resp) {
      html += `<pre style="background:var(--ok-bg);padding:10px;border-radius:6px;font-size:12px">${esc(typeof resp === 'string' ? resp : JSON.stringify(resp, null, 2))}</pre>`;
    } else {
      html += `<div class="empty">Yanıt içeriği boş</div>`;
    }

    body.innerHTML = html;
  } catch (err) {
    body.innerHTML = `<div class="empty bad">Detay yüklenemedi: ${esc(err.message)}</div>`;
  }
}

async function clearAllHistory() {
  if (!confirm('Son kaydedilen istek geçmişinin tümü silinecek. Emin misiniz?')) return;
  try {
    const res = await fetch('/__bayqus/history/clear', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({})
    });
    const j = await res.json();
    alert(j.mesaj || 'Temizlendi');
    loadHistory(0);
  } catch (err) {
    alert('Hata: ' + err.message);
  }
}

// Live polling
let lastSig = null;
async function tick(force=false){
  try{
    const r = await fetch('/__bayqus/data', {cache:'no-store'});
    const d = await r.json();
    document.getElementById('live-dot').className = 'dot';
    const sig = JSON.stringify(d, (k,v) => k==='guncellendi' ? undefined : v);
    if(!force && sig === lastSig){
      document.getElementById('last-update').textContent = `Güncellendi: ${d.guncellendi}`;
      return;
    }
    lastSig = sig;
    renderAll(d);
  }catch(e){
    document.getElementById('live-dot').className = 'dot bad';
    document.getElementById('last-update').textContent = 'Bağlantı kesildi: ' + e.message;
  }
}

tick(true);
setInterval(() => {
  if(document.getElementById('auto-refresh').checked) tick(false);
}, 4000);
</script>
</body>
</html>
"""
