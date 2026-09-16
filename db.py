"""
Bayqus Proxy SQLite Veritabani ve Prefix Onbellek Yonetimi.
WAL modunda yuksek performansli yerel onbellek.
"""
import sqlite3
import os
import json
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
DB_PATH = os.path.join(LOGS_DIR, "bayqus.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")

    # 1. Prefix Onbellek Tablosu (Byte-Identical Prompt Cache Koruyucu)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pruned_prefix_cache (
            prefix_hash TEXT PRIMARY KEY,
            pruned_json TEXT NOT NULL,
            tokens_saved INTEGER NOT NULL,
            bytes_saved INTEGER NOT NULL,
            hits INTEGER DEFAULT 1,
            summary_method TEXT DEFAULT 'deterministic',
            created_at TEXT NOT NULL,
            last_hit_at TEXT NOT NULL
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_ppc_hits ON pruned_prefix_cache(hits DESC);")

    # 2. Ayarlar Tablosu
    cur.execute("""
        CREATE TABLE IF NOT EXISTS proxy_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # Varsayilan Ayarlar
    defaults = {
        "enable_pruning": "true",
        "block_size": "48",
        "keep_recent_messages": "40",
        "enable_ai_summarizer": "true",
        "summarizer_mode": "hybrid",  # hybrid | agent_only | api_only | deterministic
        "preferred_gemini_model": "gemini-3.1-flash-lite",
        "ai_studio_api_key": os.environ.get("GEMINI_API_KEY", os.environ.get("AI_STUDIO_API_KEY", "")),
    }

    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO proxy_settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM proxy_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def set_setting(key, value):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO proxy_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] db set_setting hatasi ({key}): {e}")
        return False


def get_all_settings():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT key, value FROM proxy_settings")
        rows = cur.fetchall()
        conn.close()
        return {r["key"]: r["value"] for r in rows}
    except Exception:
        return {}


def get_cached_prefix(prefix_hash):
    """
    Onbellekten 0.1 ms'de budanmis prefix'i getirir ve hit sayacini arttirir.
    """
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT pruned_json, tokens_saved, bytes_saved, hits, summary_method 
            FROM pruned_prefix_cache 
            WHERE prefix_hash = ?
        """, (prefix_hash,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        pruned_msgs = json.loads(row["pruned_json"])
        res = {
            "messages": pruned_msgs,
            "tokens_saved": row["tokens_saved"],
            "bytes_saved": row["bytes_saved"],
            "hits": row["hits"] + 1,
            "summary_method": row["summary_method"] or "deterministic"
        }

        now_iso = datetime.utcnow().isoformat()
        cur.execute("""
            UPDATE pruned_prefix_cache 
            SET hits = hits + 1, last_hit_at = ? 
            WHERE prefix_hash = ?
        """, (now_iso, prefix_hash))
        conn.commit()
        conn.close()
        return res
    except Exception as e:
        print(f"[!] get_cached_prefix hatasi: {e}")
        return None


def save_cached_prefix(prefix_hash, pruned_messages, tokens_saved, bytes_saved, summary_method="deterministic"):
    """
    Budanmis prefix'i kalici olarak SQLite'a kaydeder.
    """
    try:
        pruned_json = json.dumps(pruned_messages, ensure_ascii=False)
        now_iso = datetime.utcnow().isoformat()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO pruned_prefix_cache 
            (prefix_hash, pruned_json, tokens_saved, bytes_saved, hits, summary_method, created_at, last_hit_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (prefix_hash, pruned_json, tokens_saved, bytes_saved, summary_method, now_iso, now_iso))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] save_cached_prefix hatasi: {e}")
        return False


def get_cache_stats():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT count(*), sum(hits), sum(tokens_saved), sum(bytes_saved) FROM pruned_prefix_cache")
        row = cur.fetchone()
        conn.close()
        return {
            "entries": row[0] or 0,
            "total_hits": row[1] or 0,
            "total_tokens_saved": row[2] or 0,
            "total_bytes_saved": row[3] or 0
        }
    except Exception:
        return {"entries": 0, "total_hits": 0, "total_tokens_saved": 0, "total_bytes_saved": 0}


def clear_cache():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM pruned_prefix_cache")
        conn.commit()
        cur.execute("VACUUM")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] clear_cache hatasi: {e}")
        return False


init_db()
