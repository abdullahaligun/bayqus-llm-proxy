"""
Bayqus Proxy - Proje Hafızası (Project Memory) Yöneticisi (memory_manager.py)
Claude Desktop & Code'un yerleşik ~/.claude/projects/<proje>/memory yapısıyla %100 uyumlu
proje hafızası okuma, yazma, düzenleme, otomatik özet çıkarma ve enjeksiyon modülü.
"""
import os
import json
import re
import glob
import time
from datetime import datetime
import urllib.request
import ssl

HERE = os.path.dirname(os.path.abspath(__file__))
CLAUDE_PROJECTS_DIR = os.path.expandvars(r"%USERPROFILE%\.claude\projects")


def get_claude_projects_dir():
    return CLAUDE_PROJECTS_DIR


def decode_project_id(pid):
    """C--workspace-ProjeYat-r-mlarAS9100-IQ-DEF -> C:/workspace/ProjeYatırımlarAS9100/IQ-DEF"""
    s = pid
    if len(s) > 3 and s[1:3] == "--":
        s = s[0] + ":/" + s[3:]
    return s.replace("-", "/")


def clean_project_name(pid):
    """Proje ID'sinden temiz ve şık bir başlık türetir."""
    # Son bölümü (klasör adını) al
    parts = pid.replace("C--workspace-", "").replace("C--workspace", "Genel").split("-")
    # Anlamlı son parçayı veya kısa adı bul
    if "IQ-DEF" in pid or "IQ-DEF" in parts:
        return "IQ-DEF (Teknopark & Savunma)"
    if "IFollow" in pid:
        return "IFollow"
    if "FinIQ" in pid:
        return "FinIQ"
    if "GLOBYPRO" in pid or "GLOBY" in pid:
        return "GLOBYPRO"
    if "TicketHelper" in pid:
        return "TicketHelper"
    if "KanikUserManagement" in pid:
        return "KanikUserManagement"
    if "Carduid-App" in pid:
        return "Carduid-App"
    if "PowerAutomateDesktop" in pid:
        return "PowerAutomateDesktop"
    if "SAPHelper" in pid:
        return "SAPHelper"
    if "HukukPortal" in pid:
        return "HukukPortal"
    
    # Varsayılan temizleme
    sub = pid.replace("C--workspace-", "").replace("C--", "")
    return sub if sub else "Genel Çalışma Alanı"


def list_projects():
    """Tüm projeleri hafıza durumları ve dosya sayılarıyla listeler."""
    results = []
    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return results

    for d in os.listdir(CLAUDE_PROJECTS_DIR):
        full = os.path.join(CLAUDE_PROJECTS_DIR, d)
        if not os.path.isdir(full):
            continue

        mem_dir = os.path.join(full, "memory")
        mem_file = os.path.join(mem_dir, "MEMORY.md")
        has_memory = os.path.isfile(mem_file)

        files_count = 0
        total_bytes = 0
        latest_mtime = 0

        if os.path.isdir(mem_dir):
            for f in os.listdir(mem_dir):
                if f.endswith(".md"):
                    files_count += 1
                    fp = os.path.join(mem_dir, f)
                    try:
                        stat = os.stat(fp)
                        total_bytes += stat.st_size
                        if stat.st_mtime > latest_mtime:
                            latest_mtime = stat.st_mtime
                    except Exception:
                        pass

        results.append({
            "id": d,
            "name": clean_project_name(d),
            "path": decode_project_id(d),
            "has_memory": has_memory,
            "files_count": files_count,
            "total_bytes": total_bytes,
            "last_modified": datetime.fromtimestamp(latest_mtime).isoformat() if latest_mtime else None,
        })

    # Hafızası olanlar ve son değiştirilenler başta
    results.sort(key=lambda x: (not x["has_memory"], -(x["files_count"]), str(x["name"]).lower()))
    return results


def parse_frontmatter(text):
    """YAML frontmatter ve gövdeyi ayrıştırır."""
    meta = {}
    body = text
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            raw_meta = parts[1].strip()
            body = parts[2].strip()
            for line in raw_meta.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k in ("name", "description", "type"):
                        meta[k] = v
    return meta, body


def get_project_memory(project_id):
    """Belirli bir projenin tüm hafıza kartlarını ve MEMORY.md indeksini döner."""
    safe_pid = os.path.basename(project_id.replace("/", "").replace("\\", ""))
    proj_dir = os.path.join(CLAUDE_PROJECTS_DIR, safe_pid)
    mem_dir = os.path.join(proj_dir, "memory")

    if not os.path.isdir(mem_dir):
        return {
            "project_id": safe_pid,
            "project_name": clean_project_name(safe_pid),
            "exists": False,
            "memory_md": "",
            "files": []
        }

    mem_file = os.path.join(mem_dir, "MEMORY.md")
    memory_md_content = ""
    if os.path.isfile(mem_file):
        try:
            with open(mem_file, "r", encoding="utf-8", errors="replace") as f:
                memory_md_content = f.read()
        except Exception as e:
            memory_md_content = f"Hata: {e}"

    files = []
    for fname in os.listdir(mem_dir):
        if fname.endswith(".md") and fname != "MEMORY.md":
            fpath = os.path.join(mem_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                stat = os.stat(fpath)
                meta, body = parse_frontmatter(content)
                files.append({
                    "filename": fname,
                    "name": meta.get("name", fname.replace(".md", "")),
                    "description": meta.get("description", ""),
                    "type": meta.get("type", "project"),
                    "size_bytes": stat.st_size,
                    "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "content": content,
                    "body": body,
                })
            except Exception:
                pass

    files.sort(key=lambda x: x["filename"].lower())

    return {
        "project_id": safe_pid,
        "project_name": clean_project_name(safe_pid),
        "exists": True,
        "memory_md": memory_md_content,
        "files": files
    }


def save_memory_file(project_id, filename, content, description=""):
    """Hafıza dosyasını kaydeder veya günceller, gerekirse MEMORY.md kütüğüne ekler."""
    safe_pid = os.path.basename(project_id.replace("/", "").replace("\\", ""))
    safe_fname = os.path.basename(filename.replace("/", "").replace("\\", ""))
    if not safe_fname.endswith(".md"):
        safe_fname += ".md"

    proj_dir = os.path.join(CLAUDE_PROJECTS_DIR, safe_pid)
    mem_dir = os.path.join(proj_dir, "memory")
    os.makedirs(mem_dir, exist_ok=True)

    fpath = os.path.join(mem_dir, safe_fname)
    is_new = not os.path.exists(fpath)

    # Dosyayı kaydet
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)

    # Eğer MEMORY.md değilse ve yeni bir dosyaysa veya indekste yoksa MEMORY.md'ye ekle
    if safe_fname != "MEMORY.md":
        mem_index_path = os.path.join(mem_dir, "MEMORY.md")
        index_content = ""
        if os.path.exists(mem_index_path):
            with open(mem_index_path, "r", encoding="utf-8", errors="replace") as f:
                index_content = f.read()

        link_pattern = f"({safe_fname})"
        if link_pattern not in index_content:
            title = safe_fname.replace(".md", "").replace("-", " ").capitalize()
            desc = description if description else title
            line = f"- [{title}]({safe_fname}) — {desc}\n"
            index_content = index_content.rstrip() + "\n" + line if index_content.strip() else line
            with open(mem_index_path, "w", encoding="utf-8") as f:
                f.write(index_content)

    return True, f"{safe_fname} başarıyla kaydedildi"


def delete_memory_file(project_id, filename):
    """Hafıza dosyasını siler ve MEMORY.md içindeki referansını kaldırır."""
    safe_pid = os.path.basename(project_id.replace("/", "").replace("\\", ""))
    safe_fname = os.path.basename(filename.replace("/", "").replace("\\", ""))

    if safe_fname == "MEMORY.md":
        return False, "Ana MEMORY.md indeksi doğrudan silinemez"

    proj_dir = os.path.join(CLAUDE_PROJECTS_DIR, safe_pid)
    mem_dir = os.path.join(proj_dir, "memory")
    fpath = os.path.join(mem_dir, safe_fname)

    if os.path.exists(fpath):
        os.remove(fpath)

    # MEMORY.md içinden link satırını temizle
    mem_index_path = os.path.join(mem_dir, "MEMORY.md")
    if os.path.exists(mem_index_path):
        try:
            with open(mem_index_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            new_lines = [l for l in lines if f"({safe_fname})" not in l]
            with open(mem_index_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception:
            pass

    return True, f"{safe_fname} silindi ve indeksten kaldırıldı"


def extract_memory_with_ai(transcript_or_text, project_id, api_key="", model="gemini-3.5-flash"):
    """
    Gemini / AI modelini çağırarak konuşma veya metinden Claude MEMORY formatında
    yapılandırılmış kural ve mimari notları üretir.
    """
    if not api_key:
        # db'den al
        import db
        api_key = db.get_setting("ai_studio_api_key", "")
        if not api_key:
            return False, "AI Studio API Key bulunamadı (Ayarlar sekmesinden girin)"

    prompt = (
        "Sen uzman bir yazılım mimarısın. Aşağıdaki konuşma / çalışma metnini inceleyerek bu projeye ait "
        "KALICI MİMARİ KARARLARI, KULLANICI TERCİHLERİNİ, YASAKLARI ve KRİTİK ÇÖZÜMLERİ çıkar.\n\n"
        "Çıktıyı kesinlikle geçerli bir JSON array olarak ver. Başka hiçbir açıklama veya markdown bloğu yazma. "
        "Her bir eleman şu formatta olmalıdır:\n"
        "[\n"
        "  {\n"
        "    \"slug\": \"dosya-adi-kebab-case\",\n"
        "    \"title\": \"Kısa Anlaşılır Başlık\",\n"
        "    \"description\": \"Tek satırlık kısa özet\",\n"
        "    \"type\": \"feedback veya project veya reference\",\n"
        "    \"content\": \"Detaylı açıklama, Why (Neden) ve How to apply (Nasıl uygulanır) bölümleri.\"\n"
        "  }\n"
        "]\n\n"
        "Örnek slug: feedback-em-dash-yok, teknopark-sunum-kurallari, pptxgenjs-v4-kullanimi\n"
        "Metin:\n" + transcript_or_text[:120000]
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.1
        }
    }

    models_to_try = [model, "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash-lite"]
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        raw_text = parts[0]["text"].strip()
                        # JSON temizliği
                        clean_json = raw_text
                        if clean_json.startswith("```"):
                            clean_json = clean_json.split("\n", 1)[1]
                            if clean_json.endswith("```"):
                                clean_json = clean_json.rsplit("```", 1)[0]
                        clean_json = clean_json.strip()

                        items = json.loads(clean_json)
                        if isinstance(items, list) and items:
                            saved_count = 0
                            for it in items:
                                slug = it.get("slug") or f"memory-{int(time.time())}"
                                title = it.get("title") or slug
                                desc = it.get("description") or title
                                mtype = it.get("type") or "project"
                                body = it.get("content") or desc

                                md_text = (
                                    f"---\n"
                                    f"name: {slug}\n"
                                    f"description: {desc}\n"
                                    f"metadata:\n"
                                    f"  node_type: memory\n"
                                    f"  type: {mtype}\n"
                                    f"  modified: {datetime.utcnow().isoformat()}Z\n"
                                    f"---\n\n"
                                    f"## {title}\n\n"
                                    f"{body}\n"
                                )
                                ok, _ = save_memory_file(project_id, f"{slug}.md", md_text, description=desc)
                                if ok:
                                    saved_count += 1

                            return True, f"{saved_count} adet yeni hafıza maddesi başarıyla çıkarıldı ve kaydedildi ({m})"
        except Exception as e:
            continue

    return False, "Yapay zekâ modeli ile hafıza çıkarma başarısız oldu"


def build_system_memory_injection(project_path_or_id, max_chars=3200):
    """
    Modelin system yönergesine enjekte edilmek üzere hafif, temiz ve şişmeyi önleyen
    bir <project_memory> bloğu üretir.

    Anti-Bloat Garantileri:
    1. Yalnızca kural indeksini (MEMORY.md) ve kritik kuralları alır.
    2. max_chars (~800 token) bütçesini asla aşmaz; şişmeyi önler.
    3. Uzun kütüklerde 'feedback / kural / yasak' maddelerine öncelik verir.
    """
    pid = str(project_path_or_id or "").strip()
    if not pid:
        return ""

    if not os.path.isdir(CLAUDE_PROJECTS_DIR):
        return ""

    # Eşleşen proje dizinini bul
    target_id = None
    all_dirs = [d for d in os.listdir(CLAUDE_PROJECTS_DIR) if os.path.isdir(os.path.join(CLAUDE_PROJECTS_DIR, d))]

    if pid in all_dirs:
        target_id = pid
    else:
        norm = pid.replace("\\", "/").rstrip("/").lower()
        # 1. Tam eşleşme ara
        for d in all_dirs:
            dec = decode_project_id(d).rstrip("/").lower()
            if dec == norm:
                target_id = d
                break
        # 2. En spesifik (en uzun) klasör eşleşmesi ara
        if not target_id:
            for d in sorted(all_dirs, key=lambda x: len(decode_project_id(x)), reverse=True):
                dec = decode_project_id(d).rstrip("/").lower()
                if norm == dec or norm.startswith(dec + "/"):
                    target_id = d
                    break

    if not target_id:
        return ""

    mem_data = get_project_memory(target_id)
    if not mem_data.get("exists") or not mem_data.get("memory_md"):
        return ""

    raw_md = mem_data["memory_md"].strip()
    if not raw_md:
        return ""

    # Şişme Önleyici Bütçe Denetimi (Anti-Bloat Guard)
    lines = [l.strip() for l in raw_md.split("\n") if l.strip()]
    if len(raw_md) > max_chars:
        # Öncelikli satırları süz (Feedback, yasak, kural, must, never, prod)
        priority_lines = []
        other_lines = []
        for l in lines:
            ll = l.lower()
            if any(k in ll for k in ("feedback", "kural", "yasak", "never", "must", "prod", "önemli", "asla", "dikkat")):
                priority_lines.append(l)
            else:
                other_lines.append(l)

        selected = []
        cur_len = 0
        for l in priority_lines + other_lines:
            if cur_len + len(l) + 2 > max_chars - 120:
                break
            selected.append(l)
            cur_len += len(l) + 2

        dropped_count = len(lines) - len(selected)
        if dropped_count > 0:
            selected.append(f"<!-- [Anti-Bloat: {dropped_count} ek referans kartı ~/.claude/projects/ altında kayıtlıdır] -->")
        content_to_inject = "\n".join(selected)
    else:
        content_to_inject = raw_md

    summary = (
        f"\n\n<project_memory project=\"{mem_data['project_name']}\">\n"
        f"# Aktif Proje Hafızası & Mimari Kurallar (MEMORY.md):\n"
        f"{content_to_inject}\n"
        f"</project_memory>\n"
    )
    return summary


def maybe_inject_memory(parsed, sid, agent_id=None):
    """
    Eğer proje hafızası varsa ve gelen istekte henüz eklenmemişse,
    şişmeyi önleyen bütçeli <project_memory> bloğunu system yönergesine ekler.

    Dönüş: (parsed, bool injected, str mesaj)
    """
    if not parsed or not isinstance(parsed, dict):
        return parsed, False, "geçersiz gövde"

    import db
    enabled = db.get_setting("enable_memory_injection", "true")
    if enabled != "true":
        return parsed, False, "devre dışı (ayar kapalı)"

    import sessions
    proje = sessions.project_for(sid, agent_id=agent_id)
    if not proje:
        return parsed, False, "oturum için proje bulunamadı"

    max_tokens = 800
    try:
        max_tokens = int(db.get_setting("memory_max_tokens", "800"))
    except Exception:
        pass
    max_chars = max_tokens * 4

    mem_block = build_system_memory_injection(proje, max_chars=max_chars)
    if not mem_block:
        return parsed, False, "hafıza boş veya yok"

    # Mükerrerlik Denetimi (Duplication Guard):
    # Model zaten hafızaya sahipse kesinlikle tekrar ekleme
    sys_field = parsed.get("system")
    sys_text = ""
    if isinstance(sys_field, str):
        sys_text = sys_field
    elif isinstance(sys_field, list):
        sys_text = " ".join([b.get("text", "") for b in sys_field if isinstance(b, dict)])

    if "<project_memory" in sys_text:
        return parsed, False, "zaten enjekte edilmiş"

    # İlk kural satırından kontrol et
    clean_lines = [l for l in mem_block.split("\n") if l.startswith("- [")]
    if clean_lines:
        first_rule = clean_lines[0].split("]")[0].replace("- [", "")
        if first_rule and first_rule in sys_text:
            return parsed, False, "kural zaten mevcut"

    # Enjeksiyon:
    tok_est = len(mem_block) // 4
    if isinstance(sys_field, list):
        parsed["system"].append({
            "type": "text",
            "text": mem_block
        })
    elif isinstance(sys_field, str):
        parsed["system"] = sys_field + mem_block
    else:
        parsed["system"] = mem_block.strip()

    return parsed, True, f"{proje} (~{tok_est} tok)"

