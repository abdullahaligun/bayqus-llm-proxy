// Bayqus Proxy Claude Desktop Installer Script
const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const ANTHROPIC_DIR = process.env.LOCALAPPDATA
  ? path.join(process.env.LOCALAPPDATA, "AnthropicClaude")
  : path.join(process.env.USERPROFILE || "", "AppData", "Local", "AnthropicClaude");
const appDirs = fs.existsSync(ANTHROPIC_DIR) ? fs.readdirSync(ANTHROPIC_DIR).filter((f) => f.startsWith("app-")) : [];
appDirs.sort();
const latestAppDir = path.join(ANTHROPIC_DIR, appDirs[appDirs.length - 1]);
const CLAUDE_RES = path.join(latestAppDir, "resources");
const ASAR_FILE = path.join(CLAUDE_RES, "app.asar");
const BACKUP_FILE = path.join(CLAUDE_RES, "app.asar.backup");
const TEMP_DIR = path.join(CLAUDE_RES, "app-unpacked-temp");
console.log(`Hedef Claude sürümü: ${path.basename(latestAppDir)}`);

const MOD_DIR = __dirname;
const INJECTOR_SRC = path.join(MOD_DIR, "bayqus-injector.js");
const UI_SRC = path.join(MOD_DIR, "bayqus-ui.js");

console.log("=== Bayqus Claude Desktop Entegrasyonu ===");

// 1. Yedek kontrolü
if (!fs.existsSync(BACKUP_FILE)) {
  console.log("[1/5] app.asar yedekleniyor...");
  fs.copyFileSync(ASAR_FILE, BACKUP_FILE);
  console.log("      Yedek oluşturuldu: app.asar.backup");
} else {
  console.log("[1/5] app.asar.backup zaten mevcut, yedekleme atlandı.");
}

// 2. Temp klasörü hazırla ve asar'ı aç
if (fs.existsSync(TEMP_DIR)) {
  fs.rmSync(TEMP_DIR, { recursive: true, force: true });
}
console.log("[2/5] app.asar geçici klasöre açılıyor...");
execSync(`npx @electron/asar extract "${ASAR_FILE}" "${TEMP_DIR}"`, { stdio: "inherit" });

// 3. Dosyaları kopyala ve index.js'e hook ekle
console.log("[3/5] Bayqus enjeksiyon dosyaları kopyalanıyor...");
const buildDir = path.join(TEMP_DIR, ".vite", "build");
fs.copyFileSync(INJECTOR_SRC, path.join(buildDir, "bayqus-injector.js"));
fs.copyFileSync(UI_SRC, path.join(buildDir, "bayqus-ui.js"));

const indexJsPath = path.join(buildDir, "index.js");
let indexContent = fs.readFileSync(indexJsPath, "utf8");
if (!indexContent.includes("bayqus-injector.js")) {
  indexContent += '\n;try{require("./bayqus-injector.js")}catch(e){console.error("[Bayqus] Init error:",e);}\n';
  fs.writeFileSync(indexJsPath, indexContent, "utf8");
  console.log("      index.js içine hook eklendi.");
} else {
  console.log("      index.js zaten hook içeriyor.");
}

// 4. Çalışan Claude süreçlerini sonlandır
console.log("[4/5] Çalışan Claude süreçleri kapatılıyor...");
try {
  execSync("taskkill /F /IM claude.exe", { stdio: "ignore" });
} catch (e) {
  // Zaten çalışmıyor olabilir
}

// 5. Yeniden paketle
console.log("[5/5] app.asar yeniden paketleniyor...");
execSync(`npx @electron/asar pack "${TEMP_DIR}" "${ASAR_FILE}" --unpack "*.{node,dll,exe}"`, { stdio: "inherit" });

// Temizlik
fs.rmSync(TEMP_DIR, { recursive: true, force: true });

console.log("\n✅ Bayqus Claude Desktop modülü başarıyla yüklendi!");
console.log("   Claude Desktop'ı başlattığınızda arayüzün sağ üst köşesinde");
console.log("   [ 🦉 Rota: Abonelik ▾ ] seçicisini göreceksiniz.\n");
