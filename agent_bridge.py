"""
Antigravity Ajan Köprüsü (Agent Bridge).
Proxy ile Antigravity ajanları arasında dosya tabanlı (dropzone) özet iletişimi sağlar.
"""
import os
import json
import time
import ssl
import urllib.request
from datetime import datetime

DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(DIR, "bridge")
PENDING_DIR = os.path.join(BRIDGE_DIR, "pending")
READY_DIR = os.path.join(BRIDGE_DIR, "ready")

os.makedirs(PENDING_DIR, exist_ok=True)
os.makedirs(READY_DIR, exist_ok=True)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

GEMINI_MODEL_POOL = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-1.5-flash"
]


def format_transcript(messages, max_recent=500):
    """
    Mesaj dizisini ozetleyici ajanin en rahat okuyacagi temiz metne cevirir.
    Aktif Ufuk ve Eski Adimlari Unutturma (Rolling Horizon & Purge):
    - Ilk 2 mesaji (proje ana amaci ve baslangic talimati) daima korur.
    - Aradaki cok eski ara adimlari (1000+ mesaj oncesi log/grep/gecici hatalar) unutturur.
    - Kesim noktasina kadar olan son max_recent mesaji detayli inceler (256K+ baglam).
    """
    if not messages:
        return ""

    parts = []
    # 1. Proje baslangic amaci (Ilk 1-2 mesaj)
    first_msgs = messages[:2]
    parts.append("=== PROJE BASLANGIC AMACI VE ILK TALIMATLAR ===")
    for i, m in enumerate(first_msgs):
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, list):
            txts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            content = " ".join(txts)
        parts.append(f"[{i+1}. Adim - {role}]: {str(content)[:1200]}")

    # 2. Aradaki cok eski adimlar elenir (Purge / Unutturma)
    if len(messages) > max_recent + 2:
        skipped = len(messages) - (max_recent + 2)
        parts.append(f"\n[... Onceki {skipped:,} ara adim basariyla tamamlandi ve gurultuyu onlemek icin arsivden elendi ...]\n")
        recent_msgs = messages[-max_recent:]
        start_idx = len(messages) - max_recent
    else:
        recent_msgs = messages[2:]
        start_idx = 2

    # 3. Son aktif asama ve mimari adimlar
    parts.append("=== SON AKTIF ASAMA VE MIMARI ADIMLAR ===")
    for i, m in enumerate(recent_msgs, start=start_idx + 1):
        role = m.get("role", "unknown")
        content = m.get("content", "")
        if isinstance(content, list):
            txts = []
            for b in content:
                if isinstance(b, dict):
                    if b.get("type") == "text":
                        txts.append(b.get("text", ""))
                    elif b.get("type") == "tool_use":
                        txts.append(f"[Arac: {b.get('name')}]")
                    elif b.get("type") == "tool_result":
                        res_c = b.get("content", "")
                        if isinstance(res_c, str):
                            txts.append(f"[Sonuc: {res_c[:200]}]")
            content = " ".join(txts)
        parts.append(f"[{i}. Adim - {role}]: {str(content)[:500]}")

    return "\n".join(parts)


def request_agent_summary(session_key, prefix_hash, messages_slice, cut_index, model=""):
    """
    Antigravity ajaninin ozetlemesi icin bekleyen istek dosyasi olusturur.
    """
    pending_file = os.path.join(PENDING_DIR, f"{prefix_hash}.json")
    if os.path.exists(pending_file):
        return pending_file

    transcript = format_transcript(messages_slice)
    data = {
        "session_key": session_key,
        "prefix_hash": prefix_hash,
        "cut_index": cut_index,
        "message_count": len(messages_slice),
        "created_at": datetime.utcnow().isoformat(),
        "model": model,
        "transcript": transcript[:400000]
    }

    tmp_file = pending_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, pending_file)
    return pending_file


def check_agent_summary(prefix_hash):
    """
    Antigravity ajanının hazırladığı hazır özeti kontrol eder.
    Varsa içeriği döner ve pending dosyasını temizler.
    """
    ready_file = os.path.join(READY_DIR, f"{prefix_hash}.json")
    if not os.path.exists(ready_file):
        return None

    try:
        with open(ready_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        summary = data.get("summary_text")
        if summary:
            # Temizlik
            pending_file = os.path.join(PENDING_DIR, f"{prefix_hash}.json")
            if os.path.exists(pending_file):
                try:
                    os.remove(pending_file)
                except Exception:
                    pass
            return summary
    except Exception as e:
        print(f"[!] ready dosya okuma hatasi ({prefix_hash}): {e}")
    return None


def save_agent_summary(prefix_hash, summary_text, agent_name="antigravity_agent"):
    """
    Ajanın veya harici sürecin hazır özeti teslim etmesi için kullanılır.
    """
    ready_file = os.path.join(READY_DIR, f"{prefix_hash}.json")
    data = {
        "prefix_hash": prefix_hash,
        "summary_text": summary_text,
        "agent": agent_name,
        "completed_at": datetime.utcnow().isoformat()
    }
    tmp_file = ready_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, ready_file)

    # Pending'i kaldır
    pending_file = os.path.join(PENDING_DIR, f"{prefix_hash}.json")
    if os.path.exists(pending_file):
        try:
            os.remove(pending_file)
        except Exception:
            pass
    return True


def list_pending():
    """Henüz özetlenmemiş bekleyen istekleri listeler."""
    items = []
    if not os.path.exists(PENDING_DIR):
        return items
    for fname in os.listdir(PENDING_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(PENDING_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    items.append(d)
            except Exception:
                pass
    return items


def count_bridge_files():
    p = len([f for f in os.listdir(PENDING_DIR) if f.endswith(".json")]) if os.path.exists(PENDING_DIR) else 0
    r = len([f for f in os.listdir(READY_DIR) if f.endswith(".json")]) if os.path.exists(READY_DIR) else 0
    return {"pending": p, "ready": r}


def call_gemini_summary(text_to_summarize, api_key, preferred_model="gemini-3.1-flash-lite", block_index=None):
    """
    Google AI Studio Fallback Çağrısı.
    Tek bir aşamanın (delta blok) odaklı özetini 150-250 kelimede üretir.
    """
    if not api_key:
        return None, "no_api_key"

    models_to_try = [preferred_model] + [m for m in GEMINI_MODEL_POOL if m != preferred_model]

    block_title = f"{block_index + 1}. Aşama" if block_index is not None else "Bu Aşama"
    prompt = (
        f"Sen uzman bir yazılım mimarısın. Aşağıda bir yazılım geliştirme oturumunun yeni tamamlanan bir aşamasına "
        f"({block_title}) ait adımlar yer almaktadır.\n"
        "Görevin, sadece bu aşamada yapılan işleri aşağıdaki 3 başlık altında kısa, net, teknik ve yapılandırılmış bir "
        "Türkçe özet olarak çıkarmaktır (~150-250 kelime):\n\n"
        "1. **Bu Aşamada Yapılan İşler & Değiştirilen Dosyalar**: Hangi dosyalarda ne gibi kritik değişiklikler yapıldı.\n"
        "2. **Kritik Hatalar & Çözümleri**: Bu aşamada karşılaşılan ve çözülen derleme/çalışma zamanı hataları.\n"
        "3. **Ulaşılan Durum & Aktif Kararlar**: Bu aşamanın sonunda kodun ulaştığı kararlı durum ve mimari notlar.\n\n"
        "Gereksiz giriş veya selamlaşma ekleme, doğrudan 1. başlıkla başla.\n\n"
        "--- AŞAMA METNİ BAŞLANGICI ---\n" + text_to_summarize[:150000] + "\n--- AŞAMA METNİ BİTİŞİ ---"
    )

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "maxOutputTokens": 600,
            "temperature": 0.1
        }
    }
    body = json.dumps(payload).encode("utf-8")

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, context=ssl_ctx, timeout=12) as resp:
                resp_json = json.loads(resp.read().decode("utf-8"))
                candidates = resp_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        summary = parts[0]["text"].strip()
                        return summary, f"ok ({model})"
        except urllib.error.HTTPError as e:
            continue
        except Exception:
            continue

    return None, "all_models_failed"
