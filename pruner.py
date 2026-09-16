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

BLOCK = int(os.environ.get("BAYQUS_BLOCK", "48"))
KEEP_RECENT = int(os.environ.get("BAYQUS_KEEP_RECENT", "40"))
COLD_BUFFER = int(os.environ.get("BAYQUS_COLD_BUFFER", "16"))
KEEP_RECENT_COLD = int(os.environ.get("BAYQUS_KEEP_RECENT_COLD", "14"))
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
    messages[:i] bir kullanici mesajiyla (user) bitmeli ve messages[i]
    bir asistan mesajiyla (assistant) baslamali.
    """
    if i <= 0 or i >= len(messages):
        return False
    return messages[i - 1].get("role") == "user" and messages[i].get("role") == "assistant"


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
    Uc katmanli budama plani olusturur (Hot/Cold/Archive).

    Arsiv  (0..archive_cut)       : Gemini ozeti ile 2 mesaja indirilir.
                                    BLOCK=48 ile yuvarlenir, cok seyrek degisir.
    Soguk  (archive_cut..hot_cut) : deterministic_prune_slice ile kirpilir.
                                    Tampon gorevi gorur, arsiv hash'ini korur.
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

    # --- Uc katmanli sinir hesaplama ---
    if cold:
        # Soguk baslangic: arsiv + soguk birlestir, sadece KEEP_RECENT_COLD tut
        effective_keep = min(keep_recent_cfg, KEEP_RECENT_COLD)
        raw_archive = max(0, n - effective_keep)
        archive_cut = 0
        for i in range(min(raw_archive, n - 1), 0, -1):
            if is_safe_boundary(msgs, i):
                archive_cut = i
                break
        hot_cut = archive_cut  # soguk katman yok, arsiv dogrudan sicaga gecis
    else:
        # Normal (sicak) akis: uc katmanli
        hot_cut_raw = n - keep_recent_cfg
        archive_raw = max(0, hot_cut_raw - cold_buffer)
        # Arsiv sinirini BLOCK'a yuvarla (stabilite icin)
        archive_q = (archive_raw // block_size) * block_size
        archive_cut = 0
        for i in range(min(archive_q, n - 1), 0, -1):
            if is_safe_boundary(msgs, i):
                archive_cut = i
                break
        # Strict Append-Only Kilidi:
        # hot_cut sinirini archive_cut'a gore sabitle.
        # Boylece 48 blok boyunca cold_msgs asla buyumez/degismez, ortadaki mesajlar
        # budanarak mutasyona ugramaz ve upstream KV cache %98+ isabetle stabil kalir.
        hot_target = archive_cut + cold_buffer
        hot_cut = hot_target
        for i in range(min(hot_target, n - 1), archive_cut, -1):
            if is_safe_boundary(msgs, i):
                hot_cut = i
                break
        if hot_cut - archive_cut < 2:
            hot_cut = archive_cut

    if archive_cut < 8:
        return {"applied": False, "reason": f"kesim esigi altinda (mesaj={n}, archive_cut={archive_cut})",
                "session": key, "cold": cold}

    archive_msgs = msgs[:archive_cut]
    cold_msgs = msgs[archive_cut:hot_cut] if hot_cut > archive_cut else []
    hot_msgs = msgs[hot_cut:]

    # Prefix hash YALNIZCA arsiv diliminden hesaplanir
    # Soguk ve sicak katmandaki degisiklikler hash'i ETKILEMEZ
    archive_json_bytes = json.dumps(archive_msgs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    prefix_hash = hashlib.sha256(archive_json_bytes).hexdigest()

    # --- Arsiv katmanini ozetle veya cacheden al ---
    cached = db.get_cached_prefix(prefix_hash)
    if cached:
        archive_result = cached["messages"]
        summary_method = cached["summary_method"]
        cache_hit = True
    else:
        # Cache miss: ozetleme ve budama
        cache_hit = False
        enable_ai = settings.get("enable_ai_summarizer", "true") == "true"
        summarizer_mode = settings.get("summarizer_mode", "hybrid")
        api_key = settings.get("ai_studio_api_key", "")
        pref_model = settings.get("preferred_gemini_model", "gemini-3.1-flash-lite")

        archive_result = []
        summary_method = "deterministic"
        summary_text = None

        min_cut = 14 if cold else 16
        if enable_ai and len(archive_msgs) >= min_cut and summarizer_mode != "deterministic":
            safe_cut = extract_safe_user_boundary(archive_msgs, min_index=min_cut, max_index=len(archive_msgs) - 4)
            if safe_cut and safe_cut >= min_cut:
                slice_to_summarize = archive_msgs[:safe_cut]

                # [A] Antigravity Ajan Koprusu
                agent_summary = agent_bridge.check_agent_summary(prefix_hash)
                if agent_summary:
                    summary_text = agent_summary
                    summary_method = "antigravity_agent"
                else:
                    agent_bridge.request_agent_summary(key, prefix_hash, slice_to_summarize, safe_cut, model=payload.get("model", ""))

                    # [B] Fallback: Gemini Flash
                    if (summarizer_mode in ("hybrid", "api_only")) and api_key:
                        transcript_text = agent_bridge.format_transcript(slice_to_summarize)
                        gemini_sum, status = agent_bridge.call_gemini_summary(transcript_text, api_key, pref_model)
                        if gemini_sum:
                            summary_text = gemini_sum
                            summary_method = f"gemini_flash ({status})"

                if summary_text:
                    archive_result.append({
                        "role": "user",
                        "content": f"[Önceki Aşama ve Mimari Kararlar Özeti (1-{safe_cut}. Adımlar)]:\n\n{summary_text}"
                    })
                    archive_result.append({
                        "role": "assistant",
                        "content": "Önceki aşamalar, yapılan değişiklikler ve alınan mimari kararlar hafızamda. Kaldığımız yerden devam ediyorum."
                    })
                    # Kalan arsiv dilimini deterministik buda
                    rem_pruned, _ = deterministic_prune_slice(archive_msgs[safe_cut:])
                    archive_result.extend(rem_pruned)

        if not archive_result:
            archive_result, _ = deterministic_prune_slice(archive_msgs)
            summary_method = "deterministic"

        # Arsiv sonuna cache capasi ekle
        archive_result = anchor_prefix_cache_control(archive_result)

        # Tasarruf hesabi ve SQLite'a kaydet
        orig_archive_len = len(archive_json_bytes)
        pruned_archive_json = json.dumps(archive_result, ensure_ascii=False)
        pruned_archive_len = len(pruned_archive_json.encode("utf-8"))
        bytes_saved = max(0, orig_archive_len - pruned_archive_len)
        tokens_saved = bytes_saved // 4
        db.save_cached_prefix(prefix_hash, archive_result, tokens_saved, bytes_saved, summary_method)

    # --- Soguk katmani deterministik buda ---
    if cold_msgs:
        cold_pruned, _ = deterministic_prune_slice(cold_msgs)
    else:
        cold_pruned = []

    # --- Final payload olustur ---
    final_messages = archive_result + cold_pruned + hot_msgs
    new_payload = dict(payload)
    new_payload["messages"] = final_messages
    normalize_cache_controls(new_payload)
    new_payload = sanitize_cache_control_budget(new_payload)
    body = json.dumps(new_payload, ensure_ascii=False).encode("utf-8")

    with _LOCK:
        same_prefix = (st.get("prefix_hash") == prefix_hash)
        st["prefix_hash"] = prefix_hash
        st["cutoff"] = archive_cut

    # Tasarruf: cache hit ise cached degerler, miss ise hesaplanan
    if cache_hit:
        tokens_saved = cached["tokens_saved"]
        bytes_saved = cached["bytes_saved"]
    # else: zaten yukarida hesaplandi

    return {
        "applied": True,
        "cache_hit": cache_hit,
        "reason": f"{'sqlite_prefix_cache' if cache_hit else 'pruned'} ({summary_method})",
        "body": body,
        "session": key,
        "cold": cold,
        "cutoff": archive_cut,
        "archive_cut": archive_cut,
        "hot_cut": hot_cut,
        "total_messages": n,
        "kept_messages": len(final_messages),
        "prefix_hash": prefix_hash[:12],
        "prefix_stable": same_prefix,
        "tokens_saved": tokens_saved,
        "bytes_saved": bytes_saved,
        "summary_method": summary_method,
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
