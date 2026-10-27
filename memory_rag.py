"""
Bayqus Proxy - Dinamik RAG (Retrieval-Augmented Generation) Hafıza Motoru (memory_rag.py)
Konuşmanın akışına ve kullanıcının son mesajına göre yalnızca o an ihtiyaç duyulan
proje hafıza kartlarını SQLite FTS5 + BM25 algoritmasıyla anlık (sub-millisecond) bulur ve enjekte eder.

Avantajları:
1. 29 KB'lık devasa kartların veya 80+ kartlık projelerin bağlamı şişirmesini önler.
2. Alakasız konuşmalarda 0 kart çeker (0 token israfı).
3. Yalnızca konuyla doğrudan ilgili en fazla 1-2 kartı seçer (~400-800 token).
4. Bellek içi (in-memory) / yerel SQLite FTS5 ile 0.3 ms gecikmeyle çalışır.
"""
import os
import re
import glob
import sqlite3
import hashlib
from typing import List, Dict, Tuple, Optional
import memory_manager
import sessions
import db

# Bellek içi FTS5 veritabanı bağlantısı
_FTS_CONN: Optional[sqlite3.Connection] = None
_INDEXED_MTIMES: Dict[str, float] = {}

STOP_WORDS = {
    'bir', 've', 'veya', 'ile', 'için', 'icin', 'olan', 'olarak', 'gibi', 'kadar', 'daha',
    'bunu', 'buna', 'şunu', 'böyle', 'sonra', 'önce', 'tüm', 'her', 'şey', 'cok', 'çok',
    'yeni', 'var', 'yok', 'ama', 'fakat', 'ise', 'yap', 'et', 'ol', 'bu', 'şu', 'o',
    'ben', 'sen', 'biz', 'siz', 'onlar', 'bize', 'size', 'bizi', 'sizi', 'de', 'da', 'ki',
    'mi', 'mu', 'mı', 'mü', 'diye', 'en', 'ise', 'ya', 'hem', 'tam', 'bile', 'artık',
    'plan', 'kod', 'dosya', 'ekle', 'yapalım', 'yapar', 'mısın', 'misin', 'lütfen', 'bak'
}


def get_fts_conn() -> sqlite3.Connection:
    global _FTS_CONN
    if _FTS_CONN is None:
        _FTS_CONN = sqlite3.connect(":memory:", check_same_thread=False)
        _FTS_CONN.row_factory = sqlite3.Row
        _FTS_CONN.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS project_memory_fts USING fts5(
                project_id,
                filename,
                title,
                mtype,
                description,
                body,
                tokenize='unicode61'
            )
        """)
    return _FTS_CONN


def sync_project_cards(project_id: str) -> int:
    """Projenin diskteki hafıza kartlarını FTS5 tablosuna senkronize eder."""
    proj_dir = os.path.join(memory_manager.CLAUDE_PROJECTS_DIR, project_id, "memory")
    if not os.path.isdir(proj_dir):
        return 0

    try:
        dir_mtime = os.path.getmtime(proj_dir)
    except Exception:
        dir_mtime = 0

    # Eğer son taramadan beri klasör değişmediyse atla (0.01 ms)
    if _INDEXED_MTIMES.get(project_id) == dir_mtime and dir_mtime > 0:
        return 0

    conn = get_fts_conn()
    conn.execute("DELETE FROM project_memory_fts WHERE project_id = ?", (project_id,))

    card_files = glob.glob(os.path.join(proj_dir, "*.md"))
    count = 0

    for fpath in card_files:
        fname = os.path.basename(fpath)
        if fname == "MEMORY.md":
            continue

        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as fp:
                raw_text = fp.read()
        except Exception:
            continue

        meta, body = memory_manager.parse_frontmatter(raw_text)
        title = meta.get("name") or fname.replace(".md", "")
        mtype = meta.get("type") or "project"
        desc = meta.get("description") or ""

        conn.execute("""
            INSERT INTO project_memory_fts (project_id, filename, title, mtype, description, body)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (project_id, fname, title, mtype, desc, body))
        count += 1

    conn.commit()
    _INDEXED_MTIMES[project_id] = dir_mtime
    return count


def extract_query_from_messages(messages: list) -> str:
    """Mesaj geçmişinden kullanıcının son amacını / anahtar kelimelerini ayıklar."""
    if not messages:
        return ""

    query_parts = []
    # Son 2 kullanıcı mesajı ve son 1 asistan yanıtı
    recent = messages[-4:]
    for m in reversed(recent):
        role = m.get("role")
        content = m.get("content")

        text_block = ""
        if isinstance(content, str):
            text_block = content
        elif isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    if b.get("type") == "text":
                        text_block += " " + b.get("text", "")
                    elif b.get("type") == "tool_result":
                        t_content = str(b.get("content", ""))
                        if "error" in t_content.lower() or "exception" in t_content.lower():
                            text_block += " " + t_content[:200]

        if role == "user":
            query_parts.append(text_block)
            if len(query_parts) >= 2:
                break
        elif role == "assistant" and not query_parts:
            query_parts.append(text_block[-300:])

    combined = " ".join(query_parts).strip()
    clean = re.sub(r"```.*?```", " ", combined, flags=re.DOTALL)
    clean = re.sub(r"https?://\S+", " ", clean)
    clean = re.sub(r"[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ_\-\s]", " ", clean)

    words = [w.lower() for w in clean.split() if len(w) >= 3 and not w.isdigit()]
    meaningful = [w for w in words if w not in STOP_WORDS]
    # En taze son 20 anlamlı kelimeyi sorgu olarak kullan
    return " ".join(meaningful[-20:])


def search_relevant_memories(
    project_id: str,
    query_text: str,
    max_cards: int = 2,
    max_chars_per_card: int = 2200
) -> List[Dict]:
    """
    Kullanıcının sorgusuna en uygun hafıza kartlarını BM25 ağırlıklandırma ile bulur.
    Eğer alaka skoru zayıfsa veya eşleşme yoksa boş liste döner (0 token harcar).
    """
    if not project_id or not query_text:
        return []

    sync_project_cards(project_id)
    conn = get_fts_conn()

    raw_words = [re.sub(r"[^a-zA-Z0-9çğıöşüÇĞİÖŞÜ]", "", w).lower() for w in query_text.split()]
    tokens = [w for w in raw_words if len(w) >= 3 and w not in STOP_WORDS]

    if not tokens:
        return []

    # FTS5 match sorgusu
    match_expr = " OR ".join(tokens[:12])

    try:
        # Ağırlıklar: filename=5.0, title=10.0, mtype=1.0, description=8.0, body=1.0
        cur = conn.execute("""
            SELECT filename, title, mtype, description, body,
                   bm25(project_memory_fts, 0.0, 5.0, 10.0, 1.0, 8.0, 1.0) as rank
            FROM project_memory_fts
            WHERE project_id = ? AND project_memory_fts MATCH ?
            ORDER BY rank ASC
            LIMIT ?
        """, (project_id, match_expr, max_cards * 3))
        rows = cur.fetchall()
    except Exception:
        return []

    results = []
    for r in rows:
        fname = r["filename"]
        title = r["title"]
        mtype = r["mtype"]
        desc = r["description"]
        body = r["body"]
        rank = float(r["rank"])

        # Meta alaka kontrolü (Başlıkta veya özette kelime geçiyor mu?)
        matched_in_meta = any(w in title.lower() or w in desc.lower() or w in fname.lower() for w in tokens)

        # Eğer meta eşleşmesi yoksa ve genel skor zayıfsa kesinlikle alma (Gürültüyü önler)
        if not matched_in_meta and rank > -1.5:
            continue

        # Dev kartları (örn: 29 KB kanik-v2-initiative) kırp ve özetini koru
        orig_len = len(body)
        if orig_len > max_chars_per_card:
            body = body[:max_chars_per_card].rsplit("\n", 1)[0]
            body += f"\n\n<!-- [Anti-Bloat: Uzun kartın devamı (~{orig_len // 4} tok) diskteki {fname} dosyasındadır] -->"

        results.append({
            "filename": fname,
            "title": title,
            "type": mtype,
            "description": desc,
            "body": body,
            "rank": rank,
            "tokens_est": len(body) // 4
        })

        if len(results) >= max_cards:
            break

    return results


def build_rag_memory_block(project_id: str, messages: list) -> Tuple[str, List[str]]:
    """Mesaj akışına göre enjekte edilecek XML hafıza bloğunu üretir."""
    query = extract_query_from_messages(messages)
    if not query:
        return "", []

    cards = search_relevant_memories(project_id, query, max_cards=2)
    if not cards:
        return "", []

    p_name = memory_manager.clean_project_name(project_id)
    matched_names = []

    blocks = [f'<relevant_project_memory project="{p_name}">']
    blocks.append("<!-- Bu göreve ait en alakalı mimari kural ve kısıtlamalar (RAG ile dinamik çekildi): -->")

    for c in cards:
        matched_names.append(c["filename"])
        t_label = "Kural / Geri Bildirim" if c["type"] == "feedback" else "Mimari Karar" if c["type"] == "project" else "Referans"
        blocks.append(f"\n### [{c['title']}] ({t_label} — {c['filename']})")
        if c["description"]:
            blocks.append(f"> Özet: {c['description']}")
        blocks.append(c["body"].strip())

    blocks.append("</relevant_project_memory>\n")
    return "\n".join(blocks), matched_names


def get_user_msg_text(msg: dict) -> str:
    """Kullanici mesajindaki gercek kullanici metnini cikarir (tool_result haric)."""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        txts = []
        for b in content:
            if isinstance(b, dict):
                # Eger tool_result ise, bu gercek insan prompt'u degildir
                if b.get("type") == "tool_result":
                    continue
                if b.get("type") == "text":
                    txts.append(b.get("text", ""))
            elif isinstance(b, str):
                txts.append(b)
        return " ".join(txts)
    return ""


def hash_user_msg_text(clean_text: str) -> str:
    """Kullanici prompt metninin kararli SHA256 ozetini cikarir."""
    # RAG bloku onceden eklenmisse onu ayiklayip orijinal mesaji hashle
    clean = re.sub(r'<relevant_project_memory.*?</relevant_project_memory>\s*', '', clean_text, flags=re.DOTALL).strip()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()[:16]


def inject_rag_into_user_msg(msg: dict, rag_block: str) -> dict:
    """Kullanici mesajina RAG XML blogunu basina yapistirir."""
    msg_copy = dict(msg)
    content = msg_copy.get("content")
    if isinstance(content, str):
        if "<relevant_project_memory" not in content:
            msg_copy["content"] = f"{rag_block}\n\n{content}"
    elif isinstance(content, list):
        already = any("<relevant_project_memory" in str(b.get("text", "")) for b in content if isinstance(b, dict))
        if not already:
            new_blocks = [{"type": "text", "text": rag_block}] + list(content)
            msg_copy["content"] = new_blocks
    return msg_copy


def maybe_inject_rag(parsed: dict, sid: str, agent_id: str = None) -> Tuple[dict, bool, str]:
    """
    Gelen /v1/messages isteğini inceler.
    Kök 'system' yönergesine ASLA dokunmaz (Prompt Cache bozulmasını %100 önler).
    Hafıza kartlarını doğrudan ilgili kullanıcı mesajına (role='user') yapıştırır ve
    oturum bazlı haritaya (session_rag_injections) kaydederek sonraki turlarda
    geçmiş mesajların bayt-özdeşliğini garanti eder.
    """
    if not parsed or not isinstance(parsed, dict):
        return parsed, False, "geçersiz gövde"

    # Ayar kontrolü
    enabled = db.get_setting("enable_rag_memory", "true")
    if enabled != "true":
        return parsed, False, "RAG devre dışı"

    messages = parsed.get("messages")
    if not isinstance(messages, list) or not messages:
        return parsed, False, "mesaj yok"

    # 1. Oturumun hafızadaki geçmiş enjeksiyonlarını getir (Bayt-özdeşlik koruması)
    known_injections = db.get_session_rag_injections(sid) if sid else {}
    restored_count = 0

    # 2. Geçmiş mesajlarda daha önce RAG uygulanmış olanları birebir aynı baytlarla onar
    for i, m in enumerate(messages):
        if m.get("role") == "user":
            u_text = get_user_msg_text(m)
            if u_text:
                h = hash_user_msg_text(u_text)
                if h in known_injections:
                    # Bu mesaja geçmiş turda RAG eklenmişti; tekrar ekle ki cache baytları birebir uyuşsun!
                    if "<relevant_project_memory" not in str(m.get("content")):
                        messages[i] = inject_rag_into_user_msg(m, known_injections[h])
                        restored_count += 1

    # 3. Son gerçek kullanıcı mesajını bul (tool_result haricindeki en son insan prompt'u)
    latest_user_idx = None
    latest_user_text = ""
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if m.get("role") == "user":
            txt = get_user_msg_text(m)
            # tool_result olmayan gerçek insan metni
            if txt and "<relevant_project_memory" not in txt:
                latest_user_idx = idx
                latest_user_text = txt
                break

    if latest_user_idx is None:
        msg_str = f"geçmişten {restored_count} enjeksiyon onarıldı" if restored_count else "uygun kullanıcı mesajı yok"
        return parsed, (restored_count > 0), msg_str

    latest_hash = hash_user_msg_text(latest_user_text)

    # Eğer son mesaj zaten bilinen bir enjeksiyona sahipse işlem tamam
    if latest_hash in known_injections:
        return parsed, (restored_count > 0), "son kullanıcı mesajı zaten enjekte edilmiş"

    # 4. Proje klasörünü tespit et
    proje_yol = sessions.project_for(sid, agent_id=agent_id)
    if not proje_yol:
        return parsed, (restored_count > 0), "oturum projesi belirlenemedi"

    target_id = None
    all_dirs = [d for d in os.listdir(memory_manager.CLAUDE_PROJECTS_DIR) if os.path.isdir(os.path.join(memory_manager.CLAUDE_PROJECTS_DIR, d))]
    norm = proje_yol.replace("\\", "/").rstrip("/").lower()
    for d in all_dirs:
        dec = memory_manager.decode_project_id(d).rstrip("/").lower()
        if dec == norm:
            target_id = d
            break
    if not target_id:
        for d in sorted(all_dirs, key=lambda x: len(memory_manager.decode_project_id(x)), reverse=True):
            dec = memory_manager.decode_project_id(d).rstrip("/").lower()
            if norm == dec or norm.startswith(dec + "/"):
                target_id = d
                break

    if not target_id:
        return parsed, (restored_count > 0), "proje klasörü eşleşmedi"

    # 5. RAG Kart Arama
    rag_block, matched_cards = build_rag_memory_block(target_id, messages)
    if not rag_block or not matched_cards:
        return parsed, (restored_count > 0), f"alakasız (0 kural eşleşti) - {restored_count} geçmiş korundu"

    # 6. Son kullanıcı mesajına yapıştır ve oturum haritasına kaydet
    messages[latest_user_idx] = inject_rag_into_user_msg(messages[latest_user_idx], rag_block)
    if sid:
        db.save_rag_injection(sid, latest_hash, rag_block)

    tok_est = len(rag_block) // 4
    card_str = ", ".join(matched_cards)
    return parsed, True, f"RAG [{card_str}] (~{tok_est} tok) -> Kullanıcı Mesajına Eklendi"
