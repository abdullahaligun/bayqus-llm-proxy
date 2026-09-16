# 🦉 Bayqus LLM Proxy

**Bayqus LLM Proxy**, Claude Code, Claude Desktop ve diğer yapay zekâ kodlama araçları için geliştirilmiş; **Prompt Caching (KV Cache) optimizasyonu**, **akıllı bağlam budama (Three-Tier Pruning)** ve **dinamik rota yönetimi** sağlayan yüksek performanslı bir yerel LLM ters vekil (reverse proxy) sunucusudur.

---

## 🚀 Öne Çıkan Özellikler

### 1. 🎯 Üç Katmanlı Bağlam Budama (Three-Tier Pruning)
Uzun soluklu yazılım geliştirme oturumlarında bağlam şişmesini (context bloat) önlerken, upstream LLM sunucularının Prefix KV Cache mekanizmasını korur:

```
┌──────────────────────────────────────────────────────────────────┐
│                    Tam Konuşma Geçmişi                           │
├───────────────────┬────────────────────┬─────────────────────────┤
│      ARŞİV        │       SOĞUK        │          SICAK          │
│  0..archive_cut   │ archive_cut..hot_cut│       hot_cut..son       │
│                   │                    │                         │
│  Gemini Flash     │ Deterministik      │  Hiç dokunulmaz         │
│  özeti (2 mesaj)  │ budama (kırpılmış) │  (tam metin & araçlar)  │
│  BLOCK = 48       │ 16 mesaj tampon    │  ~40 aktif mesaj        │
│  (seyrek kayar)   │ (sabit kalır)      │  (append-only)          │
└───────────────────┴────────────────────┴─────────────────────────┘
```

- **Arşiv Katmanı:** Çok eski adımlar Gemini Flash (veya yerel Antigravity ajanı) tarafından yapılandırılmış Türkçe/İngilizce teknik özete dönüştürülür.
- **Soğuk Katman:** Tekrarlayan sistem mesajları ve büyük çıktıları deterministik olarak budanır; `hot_cut` sınırı 48 adım boyunca sabit tutularak upstream KV cache isabet oranı (%90-98) maksimize edilir.
- **Sıcak Katman:** Modelin güncel bağlamı kaybetmemesi için son adımlara hiç dokunulmaz.

### 2. ⚡ SQLite WAL Prefix Cache
- Budanmış her prefix, SHA-256 imzasıyla yerel SQLite veritabanında saklanır.
- 0.1 milisaniye altında yanıt süresi ile CPU ve token maliyetini sıfıra indirir.

### 3. 📊 Gerçek Zamanlı Web Panosu (Dashboard & Sniffer)
- `http://127.0.0.1:5199/__bayqus` adresinde çalışan modern panelle:
  - Canlı token kullanımı, tasarruf edilen baytlar ve maliyet hesaplaması,
  - Prompt cache isabet oranları (% hit),
  - Aktif oturumlar ve proje bazlı yönlendirmeler anlık olarak izlenir.

### 4. 🎛️ Dinamik MCP (Model Context Protocol) Yöneticisi
- Claude Desktop ve Claude Code projelerindeki MCP sunucularını (ör. ağır ofis/takvim araçları) tek tıkla devre dışı bırakıp aktifleştirerek ~100k+ token tasarrufu sağlar.

### 5. 🔌 Çoklu İstemci Desteği
- **Claude Code CLI:** `wrapper/main.go` ile derlenen şeffaf wrapper sayesinde sıfır yapılandırma ile proxy üzerinden çalışır.
- **Claude Desktop:** `claude-desktop-mod` ile Electron arayüzüne entegre olan canlı rota seçici düğmesi.

---

## 🛠️ Kurulum & Hızlı Başlangıç

### Gereksinimler
- Python 3.10+
- (İsteğe bağlı) Go 1.20+ (CLI wrapper derlemek için)
- (İsteğe bağlı) Google Gemini API Key (Arşiv özetleyici için)

### 1. Depoyu Klonlayın
```bash
git clone https://github.com/abdullahaligun/bayqus-llm-proxy.git
cd bayqus-llm-proxy
```

### 2. Yapılandırmayı Hazırlayın
Örnek şablonu kopyalayın:
```bash
cp routes.example.json routes.json
```
`routes.json` içerisine kullanmak istediğiniz upstream adresi (standart `https://api.anthropic.com` veya özel Gateway/LiteLLM) ve API anahtarlarınızı tanımlayın.

### 3. Proxy Sunucusunu Başlatın
```bash
python proxy.py
```
Sunucu varsayılan olarak `http://127.0.0.1:5199` portunda çalışacaktır.
Yönetim paneline tarayıcınızdan erişebilirsiniz:
👉 `http://127.0.0.1:5199/__bayqus`

---

## ⚙️ Claude Araçları ile Entegrasyon

### Claude Code CLI ile Kullanım
Claude Code'u proxy üzerinden yönlendirmek için ortam değişkenini tanımlamanız yeterlidir:
```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:5199
claude
```
*(Windows PowerShell için: `$env:ANTHROPIC_BASE_URL="http://127.0.0.1:5199"`)*

Alternatif olarak `wrapper/` dizinindeki Go sarmalayıcısını derleyip `claude.exe` yerine kullanabilirsiniz:
```bash
cd wrapper
go build -o wrapper.exe main.go
```

### Claude Desktop Entegrasyonu
Claude Desktop arayüzüne rota ve model seçici eklemek için:
```bash
cd claude-desktop-mod
node install-mod.js
```
Kaldırmak için:
```bash
node uninstall-mod.js
```

---

## 🔒 Gizlilik & Güvenlik
- **Sıfır Dışa Bağımlılık:** Tüm budama, loglama ve prefix önbellekleme yerel makinenizde (`127.0.0.1`) gerçekleşir.
- **İzole Veriler:** Oturum geçmişleri, SQLite veritabanı ve loglar asla uzak depoya gönderilmez.

---

## 📄 Lisans
Bu proje [MIT Lisansı](LICENSE) ile lisanslanmıştır.
