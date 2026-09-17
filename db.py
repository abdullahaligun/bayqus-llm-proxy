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

    # 3. Oturum Blok Defteri (Session Ledger - Append-Only Zincir Sabitleyici)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS session_blocks (
            session_key    TEXT NOT NULL,
            block_index    INTEGER NOT NULL,
            right_boundary INTEGER NOT NULL,
            block_hash     TEXT NOT NULL,
            created_at     TEXT NOT NULL,
            PRIMARY KEY (session_key, block_index)
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_sb_session ON session_blocks(session_key, block_index);")

    # 4. İstek ve Yanıt Geçmişi Tablosu (Son 5000 İstek Halka Tamponu)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS request_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT,
            agent_id        TEXT,
            ts              TEXT NOT NULL,
            method          TEXT NOT NULL,
            path            TEXT NOT NULL,
            status_code     INTEGER NOT NULL,
            duration_ms     INTEGER NOT NULL,
            model           TEXT,
            model_sent      TEXT,
            route           TEXT,
            upstream        TEXT,
            system_prompt   TEXT,
            messages_json   TEXT,
            response_json   TEXT,
            usage_json      TEXT,
            prune_applied   INTEGER DEFAULT 0,
            prune_info_json TEXT,
            created_at      TEXT NOT NULL
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rh_session ON request_history(session_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rh_id_desc ON request_history(id DESC);")

    # Varsayilan Ayarlar
    defaults = {
        "enable_pruning": "true",
        "block_size": "32",
        "keep_recent_messages": "40",
        "enable_ai_summarizer": "true",
        "summarizer_mode": "hybrid",  # hybrid | agent_only | api_only | deterministic
        "preferred_gemini_model": "gemini-3.1-flash-lite",
        "ai_studio_api_key": os.environ.get("GEMINI_API_KEY", os.environ.get("AI_STUDIO_API_KEY", "")),
        "history_retention_max": "5000",
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


def get_session_blocks(session_key):
    """Sirali (block_index ARTAN) finalize edilmis blok listesi."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""SELECT block_index, right_boundary, block_hash
                       FROM session_blocks WHERE session_key = ?
                       ORDER BY block_index ASC""", (session_key,))
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[!] get_session_blocks hatasi: {e}")
        return []


def finalize_session_block(session_key, block_index, right_boundary, block_hash):
    """Blok sinirini ve hash'ini deftere kalici olarak kilitler."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        now_iso = datetime.utcnow().isoformat()
        cur.execute("""INSERT OR IGNORE INTO session_blocks
                       (session_key, block_index, right_boundary, block_hash, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (session_key, block_index, right_boundary, block_hash, now_iso))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] finalize_session_block hatasi: {e}")
        return False


def record_request(session_id="", agent_id="", method="POST", path="/v1/messages",
                   status_code=200, duration_ms=0, model=None, model_sent=None,
                   route=None, upstream=None, system_prompt=None,
                   messages=None, response_content=None, usage=None,
                   prune_applied=False, prune_info=None):
    """
    Giden ve gelen istek/yanit iceriklerini son 5000 istek halka tamponuna kaydeder.
    """
    try:
        conn = get_conn()
        cur = conn.cursor()
        now_iso = datetime.now().isoformat()

        sys_str = None
        if system_prompt is not None:
            sys_str = system_prompt if isinstance(system_prompt, str) else json.dumps(system_prompt, ensure_ascii=False)

        msgs_str = None
        if messages is not None:
            msgs_str = messages if isinstance(messages, str) else json.dumps(messages, ensure_ascii=False)

        resp_str = None
        if response_content is not None:
            resp_str = response_content if isinstance(response_content, str) else json.dumps(response_content, ensure_ascii=False)

        usage_str = json.dumps(usage or {}, ensure_ascii=False)
        prune_info_str = json.dumps(prune_info or {}, ensure_ascii=False) if prune_info else None

        cur.execute("""
            INSERT INTO request_history
            (session_id, agent_id, ts, method, path, status_code, duration_ms,
             model, model_sent, route, upstream, system_prompt, messages_json,
             response_json, usage_json, prune_applied, prune_info_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session_id, agent_id, now_iso, method, path, status_code, duration_ms,
              model, model_sent, route, upstream, sys_str, msgs_str,
              resp_str, usage_str, 1 if prune_applied else 0, prune_info_str, now_iso))

        inserted_id = cur.lastrowid
        conn.commit()

        # Periyodik halka tampon temizligi (her 25 kayitta bir)
        if inserted_id and inserted_id % 25 == 0:
            try:
                max_rec = int(get_setting("history_retention_max", "5000") or 5000)
                cur.execute("""
                    DELETE FROM request_history WHERE id <= (
                        SELECT id FROM request_history ORDER BY id DESC LIMIT 1 OFFSET ?
                    )
                """, (max_rec,))
                conn.commit()
            except Exception as e_trim:
                print(f"[!] auto trim_history hatasi: {e_trim}")

        conn.close()
        return inserted_id
    except Exception as e:
        print(f"[!] record_request hatasi: {e}")
        return None


def trim_history(max_records=5000):
    """Gecmis kayitlarini en son max_records adedine kirpar."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM request_history WHERE id <= (
                SELECT id FROM request_history ORDER BY id DESC LIMIT 1 OFFSET ?
            )
        """, (max_records,))
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return affected
    except Exception as e:
        print(f"[!] trim_history hatasi: {e}")
        return 0


def get_history(limit=50, offset=0, session_id=None, search=None):
    """
    Analiz ve pano icin istek gecmisini listeler.
    Buyuk JSON govdesi yerine mesaj adedi, boyut ve ozet doner (performansli).
    """
    try:
        conn = get_conn()
        cur = conn.cursor()

        query = """
            SELECT id, session_id, agent_id, ts, method, path, status_code,
                   duration_ms, model, model_sent, route, upstream,
                   length(messages_json) as req_bytes,
                   length(response_json) as resp_bytes,
                   usage_json, prune_applied, created_at
            FROM request_history
        """
        params = []
        conditions = []

        if session_id:
            conditions.append("session_id = ?")
            params.append(session_id)
        if search:
            conditions.append("(messages_json LIKE ? OR response_json LIKE ? OR system_prompt LIKE ?)")
            p_s = f"%{search}%"
            params.extend([p_s, p_s, p_s])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(query, tuple(params))
        rows = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["usage"] = json.loads(d["usage_json"]) if d["usage_json"] else {}
            except Exception:
                d["usage"] = {}
            if "usage_json" in d:
                del d["usage_json"]
            rows.append(d)

        # Toplam sayi
        count_q = "SELECT count(*) FROM request_history"
        if conditions:
            count_q += " WHERE " + " AND ".join(conditions)
            cur.execute(count_q, tuple(params[:-2]))
        else:
            cur.execute(count_q)
        total_count = cur.fetchone()[0]

        conn.close()
        return {"total": total_count, "items": rows}
    except Exception as e:
        print(f"[!] get_history hatasi: {e}")
        return {"total": 0, "items": []}


def get_request_detail(req_id):
    """Tek bir istegin tum giden mesajlarini ve gelen yanit icerigini dondurur."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT * FROM request_history WHERE id = ?", (req_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        for json_col in ("messages_json", "response_json", "usage_json", "prune_info_json"):
            target_key = json_col.replace("_json", "")
            if d.get(json_col):
                try:
                    d[target_key] = json.loads(d[json_col])
                except Exception:
                    d[target_key] = d[json_col]
        return d
    except Exception as e:
        print(f"[!] get_request_detail hatasi: {e}")
        return None


def clear_history():
    """Tum istek gecmisini temizler."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM request_history")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] clear_history hatasi: {e}")
        return False


def clear_cache():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM pruned_prefix_cache")
        cur.execute("DELETE FROM session_blocks")
        conn.commit()
        cur.execute("VACUUM")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] clear_cache hatasi: {e}")
        return False


init_db()
