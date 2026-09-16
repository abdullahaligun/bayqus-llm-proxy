"""
mcp_manager.py — Proje ve Grup bazli MCP Sunucu ve Arac Yonetimi.

Claude Code ve Claude Desktop'ta context window'u sisiren (189+ arac, 119k+ token)
gereksiz MCP sunucularini (Microsoft 365, Google Drive, Calendar, Gmail, Obsidian)
proje ve grup bazinda devre disi birakir (~/.claude.json -> disabledMcpServers).

Ayni zamanda Bayqus Proxy'nin istek govdesinden (tools) bu sunuculara ait
kullanilmamis araclari suzmesi icin kural saglar.
"""
import copy
import glob
import json
import os
import re
import shutil
import threading
import time

CLAUDE_JSON_PATH = os.path.expanduser("~/.claude.json")
CLAUDE_DESKTOP_CONFIG = os.path.expandvars(r"%APPDATA%\Claude\claude_desktop_config.json")
CLAUDE_SESSIONS_DIR = os.path.expandvars(r"%APPDATA%\Claude\claude-code-sessions")

_LOCK = threading.Lock()

# Bilinen standart MCP sunuculari ve kategorileri
KNOWN_SERVERS = {
    "claude.ai Microsoft 365": {
        "display_name": "Microsoft 365 (Office / Outlook / Teams)",
        "category": "office",
        "description": "100+ Word, Excel, Teams, Outlook, OneDrive aracı",
        "tokens_est": "~45k token",
        "default_for_code": False,
    },
    "claude.ai Google Drive": {
        "display_name": "Google Drive",
        "category": "office",
        "description": "Drive dosya arama ve indirme araçları",
        "tokens_est": "~25k token",
        "default_for_code": False,
    },
    "claude.ai Google Calendar": {
        "display_name": "Google Calendar",
        "category": "office",
        "description": "Takvim etkinlik ve toplantı araçları",
        "tokens_est": "~20k token",
        "default_for_code": False,
    },
    "claude.ai Gmail": {
        "display_name": "Google Gmail",
        "category": "office",
        "description": "E-posta okuma, arama ve gönderme araçları",
        "tokens_est": "~25k token",
        "default_for_code": False,
    },
    "obsidian": {
        "display_name": "Obsidian Not Defteri",
        "category": "notes",
        "description": "Obsidian yerel vault dosya sistemi",
        "tokens_est": "~5k token",
        "default_for_code": False,
    },
    "antigravity": {
        "display_name": "Antigravity MCP Köprüsü",
        "category": "coding",
        "description": "Antigravity sub-agent ve beceri yönetim araçları",
        "tokens_est": "~3k token",
        "default_for_code": True,
    },
    "chrome-devtools": {
        "display_name": "Chrome DevTools",
        "category": "coding",
        "description": "Tarayıcı denetleme ve hata ayıklama araçları",
        "tokens_est": "~8k token",
        "default_for_code": True,
    },
}


def _read_claude_json():
    """~/.claude.json dosyasini guvenle okur."""
    if not os.path.exists(CLAUDE_JSON_PATH):
        return {}
    try:
        with open(CLAUDE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[mcp_manager] ~/.claude.json okunamadi: {e}")
        return {}


def _write_claude_json(data):
    """~/.claude.json dosyasini atomik ve yedekli olarak yazar."""
    try:
        bak_path = CLAUDE_JSON_PATH + ".bak"
        if os.path.exists(CLAUDE_JSON_PATH):
            shutil.copy2(CLAUDE_JSON_PATH, bak_path)
        tmp_path = CLAUDE_JSON_PATH + f".tmp.{os.getpid()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        shutil.move(tmp_path, CLAUDE_JSON_PATH)
        return True, "Kaydedildi"
    except Exception as e:
        return False, f"Yazma hatasi: {e}"


def discover_all_servers():
    """Sistemde tanimli tum MCP sunucularini listeler."""
    found = dict(KNOWN_SERVERS)
    data = _read_claude_json()

    # 1. ~/.claude.json altindaki mcpServers
    for name, spec in (data.get("mcpServers") or {}).items():
        if name not in found:
            cmd = spec.get("command") or spec.get("type", "custom")
            found[name] = {
                "display_name": name,
                "category": "coding" if any(x in name.lower() for x in ["dev", "git", "code", "agent"]) else "custom",
                "description": f"Yerel MCP sunucusu ({cmd})",
                "tokens_est": "~5k token",
                "default_for_code": True,
            }

    # 2. claudeAiMcpEverConnected
    for name in (data.get("claudeAiMcpEverConnected") or []):
        if name not in found:
            found[name] = {
                "display_name": name,
                "category": "office",
                "description": "claude.ai bulut entegrasyonu",
                "tokens_est": "~20k token",
                "default_for_code": False,
            }

    # 3. Claude Desktop mcpServers
    if os.path.exists(CLAUDE_DESKTOP_CONFIG):
        try:
            with open(CLAUDE_DESKTOP_CONFIG, "r", encoding="utf-8") as f:
                dconf = json.load(f)
            for name, spec in (dconf.get("mcpServers") or {}).items():
                if name not in found:
                    found[name] = {
                        "display_name": name,
                        "category": "desktop",
                        "description": "Claude Desktop yerel MCP",
                        "tokens_est": "~5k token",
                        "default_for_code": True,
                    }
        except Exception:
            pass

    return found


def get_matching_project_paths(group_or_proj):
    """Verilen grup adi veya proje etiketine ait tum ~/.claude.json proje yollarini bulur."""
    data = _read_claude_json()
    all_projects = list((data.get("projects") or {}).keys())
    matched = set()

    target = (group_or_proj or "").strip().lower()
    if not target:
        return []

    keywords = [target]

    for p in all_projects:
        p_clean = p.replace("\\", "/").lower()
        if any(kw in p_clean for kw in keywords):
            matched.add(p)

    # Ayrica Claude Desktop oturum metaverilerindeki aktif yollari da ekle
    if os.path.isdir(CLAUDE_SESSIONS_DIR):
        for f in glob.glob(os.path.join(CLAUDE_SESSIONS_DIR, "**", "local_*.json"), recursive=True):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                title = (d.get("title") or "").strip().lower()
                if any(kw in title for kw in keywords):
                    for k in ["cwd", "originCwd"]:
                        v = d.get(k)
                        if v:
                            matched.add(v)
                            matched.add(v.replace("\\", "/"))
            except Exception:
                pass

    return sorted(list(matched))


def get_group_mcp_status(group_name):
    """Bir grup icin hangi MCP sunucularinin acik / kapali oldugunu doner."""
    all_servers = discover_all_servers()
    paths = get_matching_project_paths(group_name)
    data = _read_claude_json()
    projects = data.get("projects") or {}

    disabled_set = set()
    has_explicit_config = False

    for p in paths:
        p_cfg = projects.get(p)
        if isinstance(p_cfg, dict) and "disabledMcpServers" in p_cfg:
            has_explicit_config = True
            dis = p_cfg.get("disabledMcpServers") or []
            disabled_set.update(dis)

    result_servers = []
    for s_id, s_info in all_servers.items():
        is_disabled = s_id in disabled_set
        result_servers.append({
            "id": s_id,
            "display_name": s_info["display_name"],
            "category": s_info["category"],
            "description": s_info["description"],
            "tokens_est": s_info["tokens_est"],
            "disabled": is_disabled,
            "default_for_code": s_info["default_for_code"]
        })

    return {
        "group": group_name,
        "matched_paths_count": len(paths),
        "has_explicit_config": has_explicit_config,
        "servers": result_servers,
        "disabled_count": len(disabled_set),
        "total_servers": len(all_servers)
    }


def set_server_disabled(group_name, server_name, disabled: bool):
    """Bir grup icin belirli bir sunucuyu acar veya kapatir."""
    with _LOCK:
        data = _read_claude_json()
        projects = data.setdefault("projects", {})
        paths = get_matching_project_paths(group_name)

        if not paths and group_name:
            # Grup adi projeler arasinda yoksa dogrudan grup adini hedef yol olarak ekle
            paths = [group_name]

        for p in paths:
            p_entry = projects.setdefault(p, {})
            cur_dis = list(p_entry.get("disabledMcpServers") or [])
            if disabled and server_name not in cur_dis:
                cur_dis.append(server_name)
            elif not disabled and server_name in cur_dis:
                cur_dis = [x for x in cur_dis if x != server_name]
            p_entry["disabledMcpServers"] = cur_dis

        ok, msg = _write_claude_json(data)
        action_str = "kapatıldı" if disabled else "açıldı"
        return ok, f"{group_name} -> {server_name} {action_str} ({len(paths)} yol güncellendi)"


def apply_preset(group_name, preset_name):
    """Grup icin hizli mod uygular:
    - 'code': Ofis/posta/takvim sunucularini kapatir (~119k tasarruf). Antigravity ve yerelleri acik tutar.
    - 'all': Tum sunuculari acar.
    """
    all_servers = discover_all_servers()
    with _LOCK:
        data = _read_claude_json()
        projects = data.setdefault("projects", {})
        paths = get_matching_project_paths(group_name)

        if not paths and group_name:
            paths = [group_name]

        if preset_name == "code":
            # Ofis ve genel amacli toollari devre disi birak
            disabled_list = [
                s_id for s_id, s_info in all_servers.items()
                if not s_info.get("default_for_code", True)
            ]
        elif preset_name == "all":
            disabled_list = []
        else:
            return False, f"Bilinmeyen mod: {preset_name}"

        for p in paths:
            p_entry = projects.setdefault(p, {})
            p_entry["disabledMcpServers"] = list(disabled_list)

        ok, msg = _write_claude_json(data)
        mod_adi = "Kodlama Modu (Ofis Araçları Kapalı)" if preset_name == "code" else "Tüm Araçlar Açık"
        return ok, f"{group_name} -> {mod_adi} uygulandı ({len(paths)} yol güncellendi)"


def get_disabled_servers_for_session(sid, agent_id=None):
    """Oturum veya alt-ajan icin su an devre disi olan MCP sunucu adlarini doner."""
    try:
        import sessions
        meta = sessions.load_claude_desktop_metadata()
        sinfo = meta.get(sid, {})
        group = sinfo.get("group")
        cwd = sinfo.get("origin_cwd") or sinfo.get("cwd") or sessions.project_for(sid, agent_id)

        data = _read_claude_json()
        projects = data.get("projects") or {}

        # 1. CWD dogrudan projects altinda var mi?
        if cwd:
            for cand in [cwd, cwd.replace("\\", "/"), cwd.replace("/", "\\")]:
                if cand in projects and "disabledMcpServers" in projects[cand]:
                    return set(projects[cand]["disabledMcpServers"] or [])

        # 2. Grup bazli bak
        if group:
            st = get_group_mcp_status(group)
            return {s["id"] for s in st["servers"] if s["disabled"]}
    except Exception as e:
        print(f"[mcp_manager] get_disabled_servers_for_session hata: {e}")
    return set()


def sanitize_mcp_name(name):
    """Claude Code'un MCP sunucu adini tool on ekine cevirirken kullandigi temizleme."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def is_tool_from_disabled_server(tool_name, disabled_servers):
    """Bir tool_name devre disi bir sunucuya mi ait?"""
    if not tool_name or not disabled_servers:
        return False

    tn_lower = tool_name.lower()
    for s_name in disabled_servers:
        sanitized = sanitize_mcp_name(s_name).lower()
        candidates = [
            f"mcp__{sanitized}__",
            f"mcp__{s_name.lower()}__",
        ]
        if "microsoft 365" in s_name.lower():
            candidates.extend(["mcp__microsoft365_", "mcp__microsoft_365_", "mcp__m365_"])
        elif "google drive" in s_name.lower():
            candidates.extend(["mcp__googledrive_", "mcp__google_drive_", "mcp__drive_"])
        elif "google calendar" in s_name.lower():
            candidates.extend(["mcp__googlecalendar_", "mcp__google_calendar_", "mcp__calendar_"])
        elif "gmail" in s_name.lower():
            candidates.extend(["mcp__gmail_"])
        elif "obsidian" in s_name.lower():
            candidates.extend(["mcp__obsidian__", "mcp__obsidian_"])

        for c in candidates:
            if tn_lower.startswith(c):
                return True
    return False
