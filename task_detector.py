"""
Bayqus Proxy - Akıllı Görev ve Aşama Geçişi Algılayıcı (task_detector.py).
Konuşma akışındaki kullanıcı niyetlerini ve asistan yanıtlarını analiz ederek
yeni bir göreve geçilip geçilmediğini (Task Transition / Milestone) yüksek doğrulukla tespit eder.

Doğruluk Test Modu:
Kullanıcının chat arayüzünde canlı olarak doğruluk oranını gözlemleyebilmesi için
tespit edilen görev bilgilerini şık bir markdown rozeti olarak asistan yanıtının başına ekler.
"""
import re
import json
import os
from typing import Dict, Any, Optional, Tuple

# Oturum bazlı görev sayacı ve hafızası
_SESSION_TASKS: Dict[str, list] = {}

# 1. Açık Görev Geçişi Kalıpları (Yüksek Güven - %85-95)
EXPLICIT_TRANSITION_PATTERNS = [
    # Şimdi / Sıradaki / Yeni Görev
    (re.compile(r'\b(?:şimdi|simdi)\s+(?:de\s+)?(?:artık\s+)?(?:bir\s+)?(.+)', re.IGNORECASE), "Açık 'şimdi' geçiş talimatı", 0.90),
    (re.compile(r'\b(?:sıradaki|siradaki)\s+(?:iş|is|görev|gorev|adım|adim|aşama|asama)[:\s]+(.+)', re.IGNORECASE), "'Sıradaki iş/adım' bildirimi", 0.95),
    (re.compile(r'\byeni\s+(?:bir\s+)?(?:görev|gorev|özellik|ozellik|feature|sayfa|modül|modul|endpoint|tablo)[:\s]+(.+)', re.IGNORECASE), "Yeni özellik/modül başlangıcı", 0.92),
    (re.compile(r'\b(?:tamam|tamamdır|harika|süper|bitti)\s*[,.]?\s*(?:şimdi|sıradaki|artık|hadi)\s+(.+)', re.IGNORECASE), "Önceki iş onaylandı, yeni işe geçildi", 0.95),
    (re.compile(r'\b(?:bunu\s+(?:bitirdik|tamamladık|geçelim))\s*[,.]?\s*(.+)', re.IGNORECASE), "Önceki iş tamamlandı geçişi", 0.90),
    (re.compile(r'\b(?:artık|artik)\s+(.+?)\s+(?:kısmına|modülüne|bölümüne|adımına)\s+(?:geçelim|başlayalım)', re.IGNORECASE), "Yeni bölüme geçiş bildirimi", 0.92),
    (re.compile(r'\b(?:hadi\s+şimdi|haydi\s+şimdi)\s+(.+)', re.IGNORECASE), "Yeni aşama çağrısı", 0.88),

    # Aksiyon / Eylem Bazlı Geçişler
    (re.compile(r'\b(?:testleri|testlerini)\s+(?:yazalım|yaz|çalıştıralım|hazırla)', re.IGNORECASE), "Test yazımı aşamasına geçiş", 0.92),
    (re.compile(r'\b(?:commit\s+at|git\s+commit|değişiklikleri\s+commit|push\s+et|pr\s+aç)', re.IGNORECASE), "Kapanış ve versiyonlama aşaması", 0.95),
    (re.compile(r'\b(?:baştan\s+yaz|baştan\s+tasarla|refactor\s+edelim|refactoring\s+yap)', re.IGNORECASE), "Yeniden yapılandırma (Refactor) görevi", 0.90),

    # İngilizce Kalıplar
    (re.compile(r'^\s*(?:now\s+let\'s|let\'s\s+now|next\s+step|next\s+task|moving\s+on\s+to)\s+(.+)', re.IGNORECASE), "İngilizce açık görev geçişi", 0.92),
    (re.compile(r'^\s*/(test|commit|review|refactor|fix|bug|init|build|deploy)\b(.*)', re.IGNORECASE), "Slash komutuyla görev tetikleme", 0.98),
]

# 2. Devam Eden Mikro-Adım Kalıpları (Görev Değil - Negatif Filtre)
MICRO_STEP_PATTERNS = [
    re.compile(r'^\s*(?:evet|tamam|ok|y|onay|onaylıyorum|devam\s+et|devam|aynen|peki|harika|süper|eline\s+sağlık)\s*[.!]?$', re.IGNORECASE),
    re.compile(r'\b(?:çalışmadı|calismadi|hata\s+verdi|patladı|error|failed|undefined|syntax\s+error|import\s+hatası)\b', re.IGNORECASE),
    re.compile(r'\b(?:şurayı\s+düzelt|burayı\s+düzelt|tekrar\s+dene|düzeltelim|eksik\s+kalmış|yanlış\s+oldu)\b', re.IGNORECASE),
    re.compile(r'\b(?:bu\s+ne\s+demek|nasıl\s+çalışıyor|emin\s+misin|anlamadım|dosyayı\s+göster|kodu\s+incele)\b', re.IGNORECASE),
]

# 3. Asistanın Görevi Tamamladığını Gösteren Kapanış Sinyalleri
ASSISTANT_COMPLETION_PATTERNS = [
    re.compile(r'(?:başarıyla\s+(?:tamamlandı|güncellendi|oluşturuldu|kaydedildi|çalıştırıldı))', re.IGNORECASE),
    re.compile(r'(?:tüm\s+değişiklikler\s+yapıldı|görev\s+tamamlandı|commit\s+edildi)', re.IGNORECASE),
    re.compile(r'(?:testler\s+(?:geçti|başarılı|tamamlandı))', re.IGNORECASE),
]


def _extract_user_text(msg: Dict[str, Any]) -> str:
    """Kullanıcı mesajından insan tarafından yazılmış saf metni ayıklar."""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for b in content:
            if isinstance(b, dict):
                # tool_result insan promptu degildir, atla
                if b.get("type") == "text":
                    t = b.get("text", "").strip()
                    if t:
                        texts.append(t)
            elif isinstance(b, str):
                texts.append(b.strip())
        return " ".join(texts).strip()
    return ""


def _extract_assistant_text(msg: Dict[str, Any]) -> str:
    """Asistan mesajından metin özetini ayıklar."""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                texts.append(b.get("text", ""))
        return " ".join(texts)
    return ""


def _clean_task_name(raw: str) -> str:
    """Ham eşleşmeden okunabilir, şık bir görev başlığı üretir."""
    raw = raw.strip().rstrip(".:;,!?")
    # Fazla uzunsa ilk cümleyi veya 8 kelimeyi al
    words = raw.split()
    if len(words) > 8:
        raw = " ".join(words[:8]) + "…"
    # İlk harfi büyüt
    if raw:
        raw = raw[0].upper() + raw[1:]
    return raw or "Yeni Görev"


def detect_task_transition(messages: list, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Sohbet dizisindeki son kullanıcı mesajını ve asistan bağlamını inceleyerek
    görev geçişini tespit eder.
    """
    if not isinstance(messages, list) or len(messages) < 2:
        return {
            "is_transition": False,
            "confidence": 0.0,
            "task_name": "",
            "reason": "Yetersiz mesaj geçmişi",
            "task_id": 1
        }

    # 1. En son mesaj
    last_msg = messages[-1]
    user_text = _extract_user_text(last_msg)

    # Eğer son mesaj bir tool_result ise veya metin yoksa (otomatik ajan adımıdır), görev geçişi olamaz
    if not user_text:
        return {
            "is_transition": False,
            "confidence": 0.0,
            "task_name": "",
            "reason": "Ara sistem/araç adımı (insan metni yok)",
            "task_id": _get_current_task_count(session_id)
        }

    # 2. Negatif Filtre: Mikro adım veya hata düzeltme mi?
    for neg_pat in MICRO_STEP_PATTERNS:
        if neg_pat.search(user_text):
            # Kısa onay veya hata/düzeltme bildirimi -> Mevcut görev devam ediyor
            return {
                "is_transition": False,
                "confidence": 0.1,
                "task_name": "",
                "reason": "Mevcut görev içi mikro adım / hata düzeltme",
                "task_id": _get_current_task_count(session_id)
            }

    # 3. Pozitif Filtre A: Açık Görev Geçişi Kalıpları
    for pat, reason_desc, conf in EXPLICIT_TRANSITION_PATTERNS:
        m = pat.search(user_text)
        if m:
            raw_target = m.group(1) if m.groups() else user_text
            task_name = _clean_task_name(raw_target)
            task_id = _increment_task_count(session_id, task_name)
            return {
                "is_transition": True,
                "confidence": conf,
                "task_name": task_name,
                "reason": reason_desc,
                "task_id": task_id,
                "user_snippet": user_text[:120]
            }

    # 4. Pozitif Filtre B: Önceki Asistan Mesajı Tamamlanma + Yeni Talimat
    prev_assistant_text = ""
    for idx in range(len(messages) - 2, -1, -1):
        if messages[idx].get("role") == "assistant":
            prev_assistant_text = _extract_assistant_text(messages[idx])
            break

    assistant_completed = False
    for comp_pat in ASSISTANT_COMPLETION_PATTERNS:
        if comp_pat.search(prev_assistant_text):
            assistant_completed = True
            break

    # Asistan önceki işi tamamladıysa ve kullanıcı yeni bir emir veriyorsa (> 4 kelime)
    words = user_text.split()
    if assistant_completed and len(words) >= 4:
        task_name = _clean_task_name(user_text)
        task_id = _increment_task_count(session_id, task_name)
        return {
            "is_transition": True,
            "confidence": 0.82,
            "task_name": task_name,
            "reason": "Önceki görev tamamlandı & yeni bağımsız talimat geldi",
            "task_id": task_id,
            "user_snippet": user_text[:120]
        }

    return {
        "is_transition": False,
        "confidence": 0.25,
        "task_name": "",
        "reason": "Aynı görev akışı devam ediyor",
        "task_id": _get_current_task_count(session_id)
    }


def _get_current_task_count(session_id: Optional[str]) -> int:
    sid = session_id or "default"
    return len(_SESSION_TASKS.get(sid, [])) or 1


def _increment_task_count(session_id: Optional[str], task_name: str) -> int:
    sid = session_id or "default"
    if sid not in _SESSION_TASKS:
        _SESSION_TASKS[sid] = []
    _SESSION_TASKS[sid].append(task_name)
    return len(_SESSION_TASKS[sid])


def format_chat_badge(detection: Dict[str, Any]) -> str:
    """
    Kullanıcının chat arayüzünde görüntülenecek şık ve dikkat çekici markdown rozeti.
    """
    if not detection.get("is_transition"):
        return ""

    task_id = detection.get("task_id", 1)
    task_name = detection.get("task_name", "Yeni Görev")
    reason = detection.get("reason", "Görev geçişi algılandı")
    conf_pct = int(detection.get("confidence", 0.9) * 100)

    badge = (
        f"\n> 🎯 **[BAYQUS GÖREV TESPİTİ #{task_id}]**\n"
        f"> • **Yeni Görev:** {task_name}\n"
        f"> • **Gerekçe:** {reason}\n"
        f"> • **Tespit Güveni:** %{conf_pct}\n"
        f"> *(Doğruluk kontrol modu aktif)*\n\n"
    )
    return badge
