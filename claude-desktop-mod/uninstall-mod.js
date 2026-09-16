// Bayqus Proxy Claude Desktop Uninstaller Script
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

console.log("=== Bayqus Claude Desktop Kaldırma ===");

if (!fs.existsSync(BACKUP_FILE)) {
  console.error("❌ app.asar.backup bulunamadı! Geri yükleme yapılamıyor.");
  process.exit(1);
}

try {
  execSync("taskkill /F /IM claude.exe", { stdio: "ignore" });
} catch (e) {}

console.log("Orijinal app.asar geri yükleniyor...");
fs.copyFileSync(BACKUP_FILE, ASAR_FILE);

console.log("✅ Orijinal Claude Desktop başarıyla geri yüklendi!");
