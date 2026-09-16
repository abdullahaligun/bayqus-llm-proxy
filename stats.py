"""
metrics.jsonl -> ozet istatistik.

Pano bunu /__bayqus/data uzerinden JSON olarak cagirir.
Fiyatlar pricing.json'dan her cagride yeniden okunur (dosyayi duzenleyince
yeniden baslatmaya gerek yok).
"""
import json
import os
from collections import defaultdict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PRICING = os.path.join(HERE, "pricing.json")
METRICS = os.path.join(HERE, "logs", "metrics.jsonl")


def load_pricing():
    try:
        with open(PRICING, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"models": [], "fallback": {"input": 0, "output": 0,
                                           "cache_write": 0, "cache_read": 0},
                "abonelik_upstreamleri": []}


def rate_for(pricing, model):
    m = (model or "").lower()
    for r in pricing.get("models", []):
        if r.get("match", "").lower() in m:
            return r
    return pricing.get("fallback", {})


def cost_of(rate, rec):
    """USD. Girdi/cikti/cache ayri ayri fiyatlanir."""
    per = lambda tok, price: (tok or 0) / 1_000_000 * (price or 0)
    return (per(rec.get("input"), rate.get("input"))
            + per(rec.get("output"), rate.get("output"))
            + per(rec.get("cache_creation"), rate.get("cache_write"))
            + per(rec.get("cache_read"), rate.get("cache_read")))


def _host(u):
    u = (u or "").replace("https://", "").replace("http://", "")
    return u.split("/")[0].split(":")[0].lower()


def build(limit_recent=60):
    pricing = load_pricing()
    sub_hosts = set(pricing.get("abonelik_upstreamleri") or [])

    if not os.path.exists(METRICS):
        return {"hata": "metrics.jsonl yok", "istek": 0}

    tot = defaultdict(float)
    by_model = defaultdict(lambda: defaultdict(float))
    by_route = defaultdict(lambda: defaultdict(float))
    by_day = defaultdict(lambda: defaultdict(float))
    recent = []
    statuses = defaultdict(int)

    with open(METRICS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue

            model = r.get("model_sent") or r.get("model") or "?"
            route = r.get("route") or "?"
            up = _host(r.get("upstream") or "")
            rate = rate_for(pricing, model)
            usd = cost_of(rate, r)
            # Yerel taklit: upstream'e hic gitmedi, dolayisiyla hicbir
            # maliyet kovasina girmemeli.
            is_mock = r.get("phase") == "mock"
            if is_mock:
                usd = 0.0
            # upstream bilinmiyorsa (routing oncesi eski kayitlar) TAHMIN ETME:
            # ayri bir kovaya koy, yoksa abonelik trafigi gercek harcama gibi gorunur.
            kova = "usd_yok" if is_mock else (
                "usd_bilinmiyor" if not up else (
                    "usd_abonelik" if up in sub_hosts else "usd_gercek"))

            statuses[str(r.get("status"))] += 1
            day = (r.get("ts") or "")[:10]

            pr = r.get("prune") or {}
            saved = 0
            if pr.get("applied") and r.get("req_bytes") and r.get("planned_bytes"):
                saved = max(0, r["req_bytes"] - r["planned_bytes"])

            by_project = tot.setdefault("_by_project", defaultdict(lambda: defaultdict(float)))
            sid = r.get("session") or "anonim"

            for bucket, key in ((tot, None), (by_model, model),
                                (by_route, route), (by_day, day)):
                d = bucket if key is None else bucket[key]
                d["istek"] += 1
                if r.get("status") and r.get("status") >= 400:
                    d["hata"] = d.get("hata", 0) + 1
                d["input"] += r.get("input") or 0
                d["output"] += r.get("output") or 0
                d["cache_read"] += r.get("cache_read") or 0
                d["cache_creation"] += r.get("cache_creation") or 0
                d["context"] += r.get("context") or 0
                d["bytes_saved"] += saved
                d["ms"] += r.get("ms") or 0
                d[kova] += usd
                if is_mock:
                    d["mock"] += 1
                    # upstream'e gitmeyen govde: gercekten kazanilan trafik
                    d["mock_bytes"] += r.get("req_bytes") or 0

            recent.append({
                "ts": r.get("ts", "")[11:19],
                "ts_full": r.get("ts", ""),
                "model": model,
                "model_sent": r.get("model_sent"),
                "route": route,
                "upstream": r.get("upstream") or up,
                "status": r.get("status"),
                "error": r.get("error"),
                "ms": r.get("ms"),
                "context": r.get("context"),
                "input": r.get("input"),
                "output": r.get("output"),
                "cache_read": r.get("cache_read"),
                "cache_creation": r.get("cache_creation"),
                "hit": r.get("hit_pct"),
                "usd": round(usd, 6),
                "kova": kova,
                "req_bytes": r.get("req_bytes"),
                "resp_bytes": r.get("resp_bytes"),
                "saved": saved,
                "prune": bool(pr.get("applied")),
                "prune_details": pr,
                "mock": is_mock,
                "cutoff": pr.get("cutoff"),
                "messages": r.get("messages"),
                "tools": r.get("tools"),
                "session": r.get("session"),
                "agent": r.get("agent"),
            })

    def clean(d):
        return {k: (round(v, 6) if k.startswith("usd") else int(v))
                for k, v in d.items() if not k.startswith("_")}

    return {
        "toplam": clean(tot),
        "model": {k: clean(v) for k, v in sorted(by_model.items())},
        "rota": {k: clean(v) for k, v in sorted(by_route.items())},
        "gun": {k: clean(v) for k, v in sorted(by_day.items())},
        "durum": dict(statuses),
        "son": recent[-limit_recent:][::-1],
        "guncellendi": datetime.now().strftime("%H:%M:%S"),
        "fiyat_dosyasi": PRICING,
    }
