"""
Bayqus budama motoru — Faz 3: Antigravity Ajanı + Gemini Flash Hibrit Budama ve SQLite Prefix Cache.

Tasarim ilkesi: **onek bayt-ozdes kalmali.**
Budanmis onek her turda ayni baytlari uretmezse prompt cache'i her turda
sifirlanir ve budama kazandirdigindan cok daha fazlasini kaybettirir.
Bunu saglayan unsurlar:
  1. kesim noktasi 16'nin katina yuvarlanir -> 16 tur boyunca prefix sabit kalir.
  2. Kalici SQLite Prefix Cache (pruned_prefix_cache) -> onceden budanmis
     blok 0.1 ms'de bayt-bayt ayni sekilde diskten gelir.
  3. Kilometre Tasi Ozetleme (Milestone Compaction) -> Eski 1..N mesaj,
     Antigravity Ajani veya Gemini 3.1 Flash-Lite tarafindan 300 kelimelik
     yapilandirilmis mimari ozete donusturulup 2 mesaja indirgenir.
  4. Neye DOKUNULMAZ:
     * system ve tools -> cache capasi
     * son keep_recent mesaj -> modelin aktif calisma alani
"""
import copy
import hashlib
import json
import os
import threading
import time

import agent_bridge
import db

BLOCK = int(os.environ.get("BAYQUS_BLOCK", "32"))
KEEP_RECENT = int(os.environ.get("BAYQUS_KEEP_RECENT", "40"))
COLD_BUFFER = int(os.environ.get("BAYQUS_COLD_BUFFER", "12"))
KEEP_RECENT_COLD = int(os.environ.get("BAYQUS_KEEP_RECENT_COLD", "12"))
TTL = int(os.environ.get("BAYQUS_TTL", "300"))
MIN_MESSAGES = int(os.environ.get("BAYQUS_MIN_MESSAGES", "12"))

TR_THRESHOLD = int(os.environ.get("BAYQUS_TR_THRESHOLD", "500"))
TR_HEAD = int(os.environ.get("BAYQUS_TR_HEAD", "250"))
TR_TAIL = int(os.environ.get("BAYQUS_TR_TAIL", "150"))
DROP_THINKING = os.environ.get("BAYQUS_DROP_THINKING", "1") == "1"

_SESSIONS = {}
_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Oturum Kimligi ve TTL
# --------------------------------------------------------------------------
def session_key(payload, session_id=None):
    """Ayni sohbetin ardisik turlarini eslestiren kararli anahtar."""
    if session_id:
        return session_id[:16]
    msgs = payload.get("messages") or []
    first = json.dumps(msgs[0], sort_keys=True, ensure_ascii=False) if msgs else ""
    sysrepr = json.dumps(payload.get("system", ""), sort_keys=True, ensure_ascii=False)
    h = hashlib.sha256()
    h.update((payload.get("model") or "").encode())
    h.update(b"\x00")
    h.update(first[:4000].encode("utf-8", "replace"))
    h.update(b"\x00")
    h.update(str(len(sysrepr)).encode())
    return h.hexdigest()[:16]


def touch_session(key):
    """Oturumu gorulmus isaretler; onceki gorulmeden bu yana gecen sureyi doner."""
    now = time.time()
    with _LOCK:
        st = _SESSIONS.setdefault(key, {"last_seen": None, "prefix_hash": None,
                                        "cutoff": None, "turns": 0})
        prev = st["last_seen"]
        st["last_seen"] = now
        st["turns"] += 1
        return st, (now - prev) if prev is not None else None


# --------------------------------------------------------------------------
# Guvenli Kesim Noktasi Saptama
# --------------------------------------------------------------------------
def is_safe_boundary(messages, i):
    """
    i indeksinde kesmek guvenli mi?
    1. i sınır dışı olamaz.
    2. messages[i] bir tool_result olamaz (aksi takdirde onceki tool_use kopar).
    3. messages[i-1] (veya aradaki system mesajlari haric onceki mesaj)
       sonuclanmamis bir tool_use iceren assistant mesaji olamaz.
    """
    if i <= 0 or i >= len(messages):
        return False
    curr = messages[i]
    if curr.get("role") == "user":
        c = curr.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    return False
    prev_idx = i - 1
    while prev_idx >= 0 and messages[prev_idx].get("role") == "system":
        prev_idx -= 1
    if prev_idx >= 0:
        prev_m = messages[prev_idx]
        if prev_m.get("role") == "assistant":
            c = prev_m.get("content")
            if isinstance(c, list):
                for b in c:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        return False
    return True


def ensure_alternating_roles(messages):
    """
    Anthropic API kurali: 'roles must alternate between user and assistant'.
    Ayni role'e sahip ardisik mesajlari guvenli bir sekilde birlestirir.
    """
    if not messages:
        return messages
    merged = [messages[0]]
    for m in messages[1:]:
        prev = merged[-1]
        p_role = prev.get("role")
        c_role = m.get("role")
        if p_role == c_role and p_role in ("user", "assistant"):
            p_content = prev.get("content")
            c_content = m.get("content")
            blocks = []
            if isinstance(p_content, str):
                blocks.append({"type": "text", "text": p_content})
            elif isinstance(p_content, list):
                blocks.extend(p_content)
            if isinstance(c_content, str):
                blocks.append({"type": "text", "text": c_content})
            elif isinstance(c_content, list):
                blocks.extend(c_content)
            prev["content"] = blocks
        else:
            merged.append(m)
    return merged


def extract_safe_user_boundary(messages, min_index=14, max_index=None):
    """
    En son temiz kullanici prompt sinirini bulur (tool_result icermeyen gercek kullanici mesaji).
    """
    if max_index is None:
        max_index = len(messages) - 1
    best_idx = None
    for i in range(min_index, min(len(messages), max_index + 1)):
        m = messages[i]
        if m.get("role") == "user":
            content = m.get("content")
            has_tool_res = False
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        has_tool_res = True
                        break
            if not has_tool_res:
                best_idx = i
    return best_idx


def find_cutoff(messages, keep_recent, block_size=16):
    """
    BLOCK'a yuvarlanmis kesim indeksi.
    """
    n = len(messages)
    if n < MIN_MESSAGES:
        return 0
    raw = n - keep_recent
    if raw <= 0:
        return 0
    q = (raw // block_size) * block_size
    if q <= 0:
        return 0
    for i in range(min(q, n - 1), 0, -1):
        if is_safe_boundary(messages, i):
            return i
    return 0


def _clean_for_hash(messages):
    """cache_control gurultusunden temizlenmis kopya (hash icin)."""
    clean = copy.deepcopy(messages)
    for m in clean:
        c = m.get("content")
        if isinstance(c, list):
            for b in c:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
        m.pop("cache_control", None)
    return clean


def _block_hash(block_msgs):
    raw = json.dumps(_clean_for_hash(block_msgs), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_block_boundary(msgs, target, prev_boundary):
    """target'a en yakin GUVENLI sinir. prev_boundary'den once olamaz."""
    for i in range(min(target, len(msgs) - 1), prev_boundary, -1):
        if is_safe_boundary(msgs, i):
            return i
    return None  # bu turda henuz guvenli blok siniri bulunamadi


def _summarize_block(block_msgs, block_index, settings):
    """SADECE bu blogu ozetler (tum gecmisi degil). ~150-250 kelime."""
    enable_ai = settings.get("enable_ai_summarizer", "true") == "true"
    api_key = settings.get("ai_studio_api_key", "")
    pref_model = settings.get("preferred_gemini_model", "gemini-3.1-flash-lite")
    summary_text = None
    method = "deterministic"

    # Eger blok cok buyukse (orn. binlerce mesajlik Base Block), once deterministik buda
    msgs_to_format = block_msgs
    if len(block_msgs) > 64:
        msgs_to_format, _ = deterministic_prune_slice(block_msgs)

    if enable_ai and api_key:
        transcript = agent_bridge.format_transcript(msgs_to_format)
        summary_text, status = agent_bridge.call_gemini_summary(transcript, api_key, pref_model, block_index=block_index)
        if summary_text:
            method = f"gemini_flash ({status})"

    if not summary_text:
        pruned, _ = deterministic_prune_slice(block_msgs)
        summary_text = agent_bridge.format_transcript(pruned)[:2000]
        method = "deterministic"

    return [
        {"role": "user",
         "content": f"[{block_index + 1}. Aşama Özeti]:\n\n{summary_text}"},
        {"role": "assistant",
         "content": f"{block_index + 1}. aşama hafızamda. Kaldığımız yerden devam ediyorum."},
    ], method


def build_archive_chain(msgs, session_key, block_size, settings, cold=False):
    """
    Finalize edilmis bloklari ledger'dan okur, eksik olan(lar)i tamamlar,
    her biri icin (varsa) SQLite delta cache'ine bakar, yoksa Gemini/Agent
    cagirip TEK SEFERLIK ozetler. Onceki bloklara ASLA dokunmaz.
    Doner: (archive_result_messages, son_finalize_edilen_sinir, methods_used)
    """
    ledger = db.get_session_blocks(session_key)
    archive_result = []
    prev_boundary = 0
    next_index = 0
    methods_used = []

    # 0. Oturum gecerliligini dogrula (compact, geri sarma veya gecmis degisimi)
    ledger_valid = True
    p_check = 0
    for row in ledger:
        r_bound = row["right_boundary"]
        b_hash = row["block_hash"]
        if len(msgs) < r_bound:
            ledger_valid = False
            break
        if _block_hash(msgs[p_check:r_bound]) != b_hash:
            ledger_valid = False
            break
        p_check = r_bound

    if not ledger_valid:
        # Oturum compact edilmis veya mesajlar degismis; eski blok kayitlarini temizle
        db.clear_session_blocks(session_key)
        ledger = []

    # 1. Zaten finalize edilmis bloklari aynen ekle (SQLite ledger'dan, deterministik)
    for row in ledger:
        cached = db.get_cached_prefix(row["block_hash"])
        if cached:
            archive_result.extend(cached["messages"])
            methods_used.append(cached.get("summary_method") or "ledger_cache")
        prev_boundary = row["right_boundary"]
        next_index = row["block_index"] + 1

    # 2. Yeni tamamlanmis blok var mi kontrol et (append-only: sadece SONA ekle)
    keep_recent_cfg = int(settings.get("keep_recent_messages", KEEP_RECENT))
    effective_keep = KEEP_RECENT_COLD if cold else keep_recent_cfg
    cold_buffer = 0 if cold else COLD_BUFFER
    safe_max_archive = len(msgs) - effective_keep - cold_buffer

    while (safe_max_archive - prev_boundary) >= block_size:
        # Eger ilk blok (next_index == 0) devasa bir gecmisten basliyorsa (> 2 * block_size),
        # 150 ayri cagri yapmak yerine tek seferde guvenli en buyuk siniri Base Block (0) olarak alir.
        if next_index == 0 and safe_max_archive > 2 * block_size:
            target = safe_max_archive
        else:
            target = prev_boundary + block_size

        if target > safe_max_archive:
            break

        boundary = _find_block_boundary(msgs, target, prev_boundary)
        if boundary is None or boundary <= prev_boundary:
            break  # bu blok henuz guvenli bir sekilde tamamlanmadi, bekle

        block_msgs = msgs[prev_boundary:boundary]
        bhash = _block_hash(block_msgs)
        cached = db.get_cached_prefix(bhash)

        if cached:
            delta_pair = cached["messages"]
            methods_used.append(cached.get("summary_method") or "cached")
        else:
            delta_pair, method = _summarize_block(block_msgs, next_index, settings)
            pruned_json_len = len(json.dumps(delta_pair, ensure_ascii=False))
            orig_len = len(json.dumps(block_msgs, ensure_ascii=False))
            db.save_cached_prefix(bhash, delta_pair,
                                   max(0, (orig_len - pruned_json_len) // 4),
                                   max(0, orig_len - pruned_json_len),
                                   method)
            methods_used.append(method)

        db.finalize_session_block(session_key, next_index, boundary, bhash)
        archive_result.extend(delta_pair)
        prev_boundary = boundary
        next_index += 1

    return archive_result, prev_boundary, methods_used


# --------------------------------------------------------------------------
# Deterministik Dilim Budama (Saf Fonksiyon)
# --------------------------------------------------------------------------
def _shrink_text(t, head, tail, label):
    if not isinstance(t, str) or len(t) <= TR_THRESHOLD:
        return t, 0
    saved = len(t) - (head + tail)
    return (f"{t[:head]}\n\n[… {label}: {len(t):,} karakterin "
            f"{saved:,} tanesi budandi …]\n\n{t[-tail:]}", saved)


def deterministic_prune_slice(messages):
    """
    Eski mesaj dilimini deterministik olarak budar.
    """
    pruned = []
    stats = {"images": 0, "thinking": 0, "tool_results": 0, "skills": 0, "saved_chars": 0}

    for msg in messages:
        msg_copy = copy.deepcopy(msg)
        role = msg_copy.get("role")
        content = msg_copy.get("content")

        # 1. Tekrar eden eski Sistem / Beceri dokumleri
        if role == "system" and "anthropic-skills" in str(content):
            saved = len(str(content)) - 55
            stats["skills"] += 1
            stats["saved_chars"] += saved
            msg_copy["content"] = "[Eski sistem beceri tanimlari onbellekten budandi]"
            pruned.append(msg_copy)
            continue

        if isinstance(content, list):
            new_blocks = []
            for b in content:
                if not isinstance(b, dict):
                    new_blocks.append(b)
                    continue
                btype = b.get("type")

                # 2. Resimleri buda
                if btype == "image":
                    src = b.get("source") or {}
                    data = src.get("data", "")
                    dlen = len(data)
                    stats["images"] += 1
                    stats["saved_chars"] += dlen
                    new_blocks.append({
                        "type": "text",
                        "text": f"[Eski gorsel kaldirildi: {src.get('media_type', 'image')}, {dlen:,} bayt]"
                    })
                    continue

                # 3. Düşünce (thinking) blokları
                elif btype in ("thinking", "redacted_thinking"):
                    if DROP_THINKING:
                        stats["thinking"] += 1
                        stats["saved_chars"] += len(json.dumps(b, ensure_ascii=False))
                        continue
                    else:
                        th = b.get("thinking", "")
                        if len(th) > 300:
                            saved = len(th) - 130
                            stats["thinking"] += 1
                            stats["saved_chars"] += saved
                            b["thinking"] = th[:100] + f" ... [Eski dusunce sureci budandi: {len(th):,} karakter] ..."
                        new_blocks.append(b)
                        continue

                # 4. Tool result cikti kirpma
                elif btype == "tool_result":
                    res_c = b.get("content")
                    if isinstance(res_c, str):
                        new_c, saved = _shrink_text(res_c, TR_HEAD, TR_TAIL, "arac ciktisi")
                        if saved:
                            stats["tool_results"] += 1
                            stats["saved_chars"] += saved
                            b["content"] = new_c
                    elif isinstance(res_c, list):
                        out, tot = [], 0
                        for sub in res_c:
                            if isinstance(sub, dict) and sub.get("type") == "text":
                                new_sub, s = _shrink_text(sub.get("text", ""), TR_HEAD, TR_TAIL, "arac ciktisi")
                                tot += s
                                out.append(dict(sub, text=new_sub) if s else sub)
                            elif isinstance(sub, dict) and sub.get("type") == "image":
                                src = sub.get("source") or {}
                                dlen = len(src.get("data", ""))
                                tot += dlen
                                out.append({"type": "text", "text": f"[gorsel budandi: {dlen:,} bayt]"})
                            else:
                                out.append(sub)
                        if tot:
                            stats["tool_results"] += 1
                            stats["saved_chars"] += tot
                        b["content"] = out
                    new_blocks.append(b)
                    continue

                # 5. Metin ici beceri tekrarlari
                elif btype == "text":
                    txt = b.get("text", "")
                    if "anthropic-skills" in txt and len(txt) > 1000:
                        saved = len(txt) - 55
                        stats["skills"] += 1
                        stats["saved_chars"] += saved
                        b["text"] = "[Eski sistem beceri tanimlari onbellekten budandi]"

                new_blocks.append(b)

            if not new_blocks:
                new_blocks = [{"type": "text", "text": "[budandi]"}]
            msg_copy["content"] = new_blocks

        elif isinstance(content, str) and len(content) > 3000:
            # Yapistirilmis dev loglar / dump'lar
            orig_len = len(content)
            head = content[:1500]
            tail = content[-500:]
            saved = orig_len - (len(head) + len(tail) + 60)
            stats["saved_chars"] += saved
            msg_copy["content"] = f"{head}\n\n[… Yapistirilmis dev metin: {orig_len:,} karakterin {saved:,} tanesi budandi …]\n\n{tail}"

        pruned.append(msg_copy)

    return pruned, stats


def anchor_prefix_cache_control(messages):
    """
    Dondurulan prefix diliminin son mesajina kalici {'type': 'ephemeral'}
    capasi ekler. Dilim icindeki eski ara cache_control bloklarini temizler
    boylece Anthropic'in 4 breakpoint butcesi korunur ve prefix 16 tur sabit kalir.
    """
    if not messages:
        return messages

    anchored = []
    for m in messages:
        mc = copy.deepcopy(m)
        content = mc.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and "cache_control" in b:
                    del b["cache_control"]
        elif isinstance(mc, dict) and "cache_control" in mc:
            del mc["cache_control"]
        anchored.append(mc)

    last_m = anchored[-1]
    content = last_m.get("content")
    if isinstance(content, str):
        last_m["content"] = [
            {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
        ]
    elif isinstance(content, list) and content:
        last_b = content[-1]
        if isinstance(last_b, dict):
            last_b["cache_control"] = {"type": "ephemeral"}
        else:
            content.append({"type": "text", "text": "", "cache_control": {"type": "ephemeral"}})
    elif not content:
        last_m["content"] = [
            {"type": "text", "text": "", "cache_control": {"type": "ephemeral"}}
        ]

    return anchored


def sanitize_cache_control_budget(payload, max_allowed=4):
    """
    Payload icerisindeki toplam cache_control blok sayisini 4 ile sinirlar.
    Sistem (2) + Sabit Prefix Capasi (1) + En Son Kullanici Mesaji (1) = 4.
    Aradaki gereksiz tum ara breakpoint'leri eler.
    """
    system = payload.get("system", [])
    tools = payload.get("tools", [])
    msgs = payload.get("messages", [])

    markers = []
    if isinstance(system, list):
        for s in system:
            if isinstance(s, dict) and "cache_control" in s:
                markers.append(("system", s))
    for t in tools:
        if isinstance(t, dict) and "cache_control" in t:
            markers.append(("tool", t))

    for m_idx, m in enumerate(msgs):
        content = m.get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and "cache_control" in b:
                    markers.append(("msg", m_idx, b))
        elif isinstance(m, dict) and "cache_control" in m:
            markers.append(("msg_dict", m_idx, m))

    sys_markers = [item for item in markers if item[0] == "system"]
    if len(sys_markers) > 1:
        for item in sys_markers[:-1]:
            if "cache_control" in item[1]:
                del item[1]["cache_control"]

    if len(markers) <= max_allowed:
        return payload

    excess = len(markers) - max_allowed
    msg_markers = [item for item in markers if item[0] in ("msg", "msg_dict")]

    # Mesajlarda birden fazla marker varsa:
    # Ilk mesaji (prefix capasi) ve son mesaji (guncel tur) koru, aradakileri sil
    if len(msg_markers) > 2:
        for item in msg_markers[1:-1]:
            if excess <= 0:
                break
            target = item[2] if item[0] == "msg" else item[1]
            if isinstance(target, dict) and "cache_control" in target:
                del target["cache_control"]
                excess -= 1

    # Eger hala bütçe aşıldıysa sondan başa doğru (en sonuncu haric) temizle
    if excess > 0 and len(msg_markers) > 1:
        for item in reversed(msg_markers[:-1]):
            if excess <= 0:
                break
            target = item[2] if item[0] == "msg" else item[1]
            if isinstance(target, dict) and "cache_control" in target:
                del target["cache_control"]
                excess -= 1

    return payload



def normalize_cache_controls(obj):
    """
    Gateway uyumlulugu: Bazi upstream gateway'ler (LiteLLM, vLLM, OneAPI vb.) Anthropic'in
    1 saatlik extended-cache-ttl ('ttl': '1h') ve 'scope': 'global' etiketlerini
    mesajlar uzerinde desteklememektedir ve bu etiketler var oldugunda mesaj onbellegini
    tamamen iptal etmektedir (22.400 tokende kilitlenir).
    Bu fonksiyon tum cache_control nesnelerini standart {'type': 'ephemeral'}
    formatina donusturerek gateway'in %90+ onbellek vurmasini saglar.
    """
    if isinstance(obj, dict):
        if "cache_control" in obj and isinstance(obj["cache_control"], dict):
            obj["cache_control"] = {"type": "ephemeral"}
        for v in obj.values():
            normalize_cache_controls(v)
    elif isinstance(obj, list):
        for item in obj:
            normalize_cache_controls(item)
    return obj


# --------------------------------------------------------------------------
# Ana Planlama Fonksiyonu
# --------------------------------------------------------------------------
def plan(payload, session_id=None):
    """
    Immutable Append-Only Delta Ledger budama plani (Hot/Cold/Archive).

    Arsiv  (0..archive_cut)       : SQLite Session Ledger tarafindan kilitlenmis,
                                    her blok (32 adim) kendi (user, assistant) ciftinde
                                    donmus ve asla degismeyen delta ozetler zinciri.
    Soguk  (archive_cut..hot_cut) : deterministic_prune_slice ile kirpilir.
                                    Tampon gorevi gorur, arsiv zincirini korur.
    Sicak  (hot_cut..son)         : Hic dokunulmaz, tam metin.

    payload'i DEGISTIRMEZ.
    """
    msgs = payload.get("messages")
    if not isinstance(msgs, list):
        return {"applied": False, "reason": "mesaj yok"}

    settings = db.get_all_settings()
    block_size = int(settings.get("block_size", BLOCK))
    keep_recent_cfg = int(settings.get("keep_recent_messages", KEEP_RECENT))
    cold_buffer = COLD_BUFFER

    n = len(msgs)
    key = session_key(payload, session_id)
    st, since = touch_session(key)
    cold = since is None or since >= TTL

    # 1. Immutable Append-Only Ledger Zinciri
    archive_result, archive_cut, methods_used = build_archive_chain(
        msgs, key, block_size, settings, cold=cold
    )

    if archive_cut < 8 or archive_cut >= n:
        # Henuz ilk blok finalize edilmedi veya kesim esigi altinda / oturum boyutu yetersiz
        return {"applied": False, "reason": f"kesim esigi altinda (mesaj={n}, archive_cut={archive_cut})",
                "session": key, "cold": cold}

    # 2. Soguk ve Sicak Dilim Sinirlari (Cold path ledger'i bozmaz, sadece tamponu/sicagi daraltir)
    hot_target = archive_cut + (0 if cold else cold_buffer)
    hot_cut = hot_target
    for i in range(min(hot_target, n - 1), archive_cut, -1):
        if is_safe_boundary(msgs, i):
            hot_cut = i
            break
    if hot_cut - archive_cut < 2:
        hot_cut = archive_cut

    archive_msgs = msgs[:archive_cut]
    cold_msgs = msgs[archive_cut:hot_cut] if hot_cut > archive_cut else []
    hot_msgs = msgs[hot_cut:]

    # 3. Soguk katmani deterministik buda
    if cold_msgs:
        cold_pruned, _ = deterministic_prune_slice(cold_msgs)
    else:
        cold_pruned = []

    # 4. Arsiv sonuna cache capasi ekle
    archive_result_anchored = anchor_prefix_cache_control(archive_result)

    # 5. Final payload olustur
    final_messages = ensure_alternating_roles(archive_result_anchored + cold_pruned + hot_msgs)
    new_payload = dict(payload)
    new_payload["messages"] = final_messages
    normalize_cache_controls(new_payload)
    new_payload = sanitize_cache_control_budget(new_payload)
    body = json.dumps(new_payload, ensure_ascii=False).encode("utf-8")

    # Tasarruf hesabi
    orig_archive_len = len(json.dumps(archive_msgs, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    pruned_archive_len = len(json.dumps(archive_result, ensure_ascii=False).encode("utf-8"))
    bytes_saved = max(0, orig_archive_len - pruned_archive_len)
    tokens_saved = bytes_saved // 4

    summary_method_str = ", ".join(methods_used[-2:]) if methods_used else "ledger_chain"
    prefix_hash = f"ledger_{key[:8]}_b{archive_cut}"

    with _LOCK:
        same_prefix = (st.get("prefix_hash") == prefix_hash)
        st["prefix_hash"] = prefix_hash
        st["cutoff"] = archive_cut

    return {
        "applied": True,
        "cache_hit": True,
        "reason": f"ledger_chain ({summary_method_str})",
        "body": body,
        "session": key,
        "cold": cold,
        "cutoff": archive_cut,
        "archive_cut": archive_cut,
        "hot_cut": hot_cut,
        "total_messages": n,
        "kept_messages": len(final_messages),
        "prefix_hash": prefix_hash,
        "prefix_stable": same_prefix,
        "tokens_saved": tokens_saved,
        "bytes_saved": bytes_saved,
        "summary_method": summary_method_str,
        "stats": {"images": 0, "thinking": 0, "tool_results": 0, "skills": 0,
                  "saved_chars": bytes_saved,
                  "archive_msgs": len(archive_msgs), "cold_msgs": len(cold_msgs),
                  "hot_msgs": len(hot_msgs)},
    }


def prune_tools(payload, disabled_servers=None):
    """
    Istek govdesindeki 'tools' dizisinden devre disi birakilmis MCP sunucularina ait
    ve gecmiste hic KULLANILMAMIS araclari eler.
    """
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools or not disabled_servers:
        return payload, {"pruned_tools": 0, "saved_bytes": 0, "kept_tools": len(tools or [])}

    import mcp_manager

    used_tools = set()
    msgs = payload.get("messages") or []
    for m in msgs:
        content = m.get("content")
        if isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict):
                    if blk.get("type") == "tool_use":
                        t_name = blk.get("name")
                        if t_name:
                            used_tools.add(t_name)

    kept_tools = []
    pruned_count = 0
    saved_bytes = 0

    for t in tools:
        if not isinstance(t, dict):
            kept_tools.append(t)
            continue
        t_name = t.get("name") or ""
        if mcp_manager.is_tool_from_disabled_server(t_name, disabled_servers):
            if t_name in used_tools:
                kept_tools.append(t)
            else:
                pruned_count += 1
                try:
                    saved_bytes += len(json.dumps(t, ensure_ascii=False))
                except Exception:
                    saved_bytes += 300
        else:
            kept_tools.append(t)

    if pruned_count > 0:
        new_payload = dict(payload)
        new_payload["tools"] = kept_tools
        return new_payload, {
            "pruned_tools": pruned_count,
            "saved_bytes": saved_bytes,
            "kept_tools": len(kept_tools),
            "total_tools": len(tools)
        }

    return payload, {
        "pruned_tools": 0,
        "saved_bytes": 0,
        "kept_tools": len(tools),
        "total_tools": len(tools)
    }
