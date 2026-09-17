#!/usr/bin/env python3
"""
Bayqus Proxy İstek ve Yanıt Geçmişi Analiz Aracı (history_analyzer.py).
Son 5000 isteğe kadar kaydedilen giden/gelen mesajları inceler, arar ve dışa aktarır.

Kullanım Örnekleri:
    python history_analyzer.py --list
    python history_analyzer.py --list --limit 20 --session <session_id>
    python history_analyzer.py --show 42
    python history_analyzer.py --search "InvoiceService"
    python history_analyzer.py --stats
    python history_analyzer.py --export istekler.jsonl
"""
import sys
import os
import json
import argparse
from datetime import datetime

# Modülleri bulabilmek için çalışma dizinini ekle
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import db


def format_bytes(n):
    if n is None:
        return "-"
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def cmd_list(args):
    data = db.get_history(limit=args.limit, offset=args.offset,
                          session_id=args.session, search=args.search)
    total = data.get("total", 0)
    items = data.get("items", [])

    print(f"\n=== Bayqus Proxy İstek Geçmişi (Toplam: {total:,}, Gösterilen: {len(items)}) ===")
    if not items:
        print("Kayıtlı istek bulunamadı.\n")
        return

    print(f"{'ID':<6} {'ZAMAN':<19} {'DURUM':<6} {'SÜRE':<8} {'MODEL':<20} {'GİRDİ':<8} {'ÇIKTI':<8} {'BOYUT':<10} {'OTURUM'}")
    print("-" * 100)
    for it in items:
        rid = it["id"]
        ts = (it["ts"] or "")[:19].replace("T", " ")
        status = it["status_code"]
        dur = f"{it['duration_ms']}ms"
        model = (it["model"] or "-")[:18]
        u = it.get("usage") or {}
        inp = u.get("input_tokens", 0)
        out = u.get("output_tokens", 0)
        req_b = format_bytes(it.get("req_bytes"))
        sid = (it.get("session_id") or "")[:12]
        if it.get("prune_applied"):
            model += "*"

        print(f"{rid:<6} {ts:<19} {status:<6} {dur:<8} {model:<20} {inp:<8} {out:<8} {req_b:<10} {sid}")
    print()


def cmd_show(args):
    req = db.get_request_detail(args.id)
    if not req:
        print(f"\n[!] ID={args.id} olan istek bulunamadı.\n")
        return

    print(f"\n{'='*35} İSTEK DETAYI (ID: {req['id']}) {'='*35}")
    print(f"Zaman:       {req.get('ts')}")
    print(f"Metot/Yol:   {req.get('method')} {req.get('path')}")
    print(f"Durum:       {req.get('status_code')} ({req.get('duration_ms')} ms)")
    print(f"Model:       {req.get('model')} (Gönderilen: {req.get('model_sent')})")
    print(f"Rota/Hedef:  {req.get('route')} -> {req.get('upstream')}")
    print(f"Oturum ID:   {req.get('session_id')} (Alt Ajan: {req.get('agent_id') or '-'})")

    u = req.get("usage") or {}
    print(f"Tokenlar:    Girdi: {u.get('input_tokens', 0):,} | Çıktı: {u.get('output_tokens', 0):,} | "
          f"Cache-Oku: {u.get('cache_read_input_tokens', 0):,} | Cache-Yaz: {u.get('cache_creation_input_tokens', 0):,}")

    if req.get("prune_applied"):
        p_info = req.get("prune_info") or {}
        print(f"Budama:      UYGULANDI (Kesim: {p_info.get('cutoff')}, Sebep: {p_info.get('reason')})")

    sys_p = req.get("system_prompt")
    if sys_p:
        print(f"\n--- SİSTEM YÖNERGESİ (Uzunluk: {len(sys_p):,} karakter) ---")
        preview = sys_p if args.full else (sys_p[:300] + ("..." if len(sys_p) > 300 else ""))
        print(preview)

    msgs = req.get("messages")
    print(f"\n--- GİDEN MESAJLAR (Toplam: {len(msgs) if isinstance(msgs, list) else 0} mesaj) ---")
    if isinstance(msgs, list):
        for idx, m in enumerate(msgs):
            role = m.get("role", "unknown").upper()
            c = m.get("content", "")
            print(f"\n[{idx+1}] {role}:")
            if isinstance(c, str):
                preview = c if args.full else (c[:300] + ("..." if len(c) > 300 else ""))
                print(f"    {preview.strip()}")
            elif isinstance(c, list):
                for b_idx, block in enumerate(c):
                    if isinstance(block, dict):
                        btype = block.get("type", "unknown")
                        if btype == "text":
                            txt = block.get("text", "")
                            p = txt if args.full else (txt[:250] + ("..." if len(txt) > 250 else ""))
                            print(f"    [blok {b_idx} text] {p.strip()}")
                        elif btype == "tool_use":
                            name = block.get("name")
                            inp_s = json.dumps(block.get("input", {}), ensure_ascii=False)
                            p = inp_s if args.full else (inp_s[:200] + ("..." if len(inp_s) > 200 else ""))
                            print(f"    [blok {b_idx} tool_use: {name}] {p}")
                        elif btype == "tool_result":
                            res_c = block.get("content", "")
                            res_s = res_c if isinstance(res_c, str) else json.dumps(res_c, ensure_ascii=False)
                            p = res_s if args.full else (res_s[:250] + ("..." if len(res_s) > 250 else ""))
                            print(f"    [blok {b_idx} tool_result ({block.get('tool_use_id', '')})] {p.strip()}")
                        elif btype == "thinking":
                            th = block.get("thinking", "")
                            p = th if args.full else (th[:150] + ("..." if len(th) > 150 else ""))
                            print(f"    [blok {b_idx} thinking] {p.strip()}")
                        else:
                            print(f"    [blok {b_idx} {btype}]")
                    else:
                        print(f"    {str(block)[:200]}")

    resp = req.get("response")
    print(f"\n--- GELEN ASİSTAN YANITI ---")
    if isinstance(resp, list):
        for idx, block in enumerate(resp):
            if isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    txt = block.get("text", "")
                    p = txt if args.full else (txt[:600] + ("..." if len(txt) > 600 else ""))
                    print(f"[text] {p}")
                elif btype == "tool_use":
                    name = block.get("name")
                    inp_s = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2 if args.full else None)
                    p = inp_s if args.full else (inp_s[:300] + ("..." if len(inp_s) > 300 else ""))
                    print(f"[tool_use: {name}] {p}")
                elif btype == "error":
                    print(f"[ERROR] {block.get('error') or block.get('message')}")
                else:
                    print(f"[{btype}] {json.dumps(block, ensure_ascii=False)}")
            else:
                print(str(block))
    elif isinstance(resp, dict):
        print(json.dumps(resp, ensure_ascii=False, indent=2))
    elif resp:
        print(str(resp))
    else:
        print("(Yanıt içeriği kaydedilmemiş veya boş)")

    print(f"\n{'='*85}\n")


def cmd_stats(args):
    conn = db.get_conn()
    cur = conn.cursor()

    cur.execute("SELECT count(*), min(ts), max(ts) FROM request_history")
    total, min_ts, max_ts = cur.fetchone()

    cur.execute("""
        SELECT model, count(*) as c
        FROM request_history GROUP BY model ORDER BY c DESC LIMIT 10
    """)
    models = cur.fetchall()

    cur.execute("""
        SELECT status_code, count(*) as c
        FROM request_history GROUP BY status_code ORDER BY c DESC
    """)
    statuses = cur.fetchall()

    cur.execute("""
        SELECT avg(duration_ms) FROM request_history WHERE status_code = 200
    """)
    avg_dur = cur.fetchone()[0] or 0

    conn.close()

    print("\n=== Bayqus Proxy İstek Geçmişi İstatistikleri ===")
    print(f"Toplam Kayıtlı İstek: {total:,}")
    print(f"Zaman Aralığı:         {(min_ts or '-')[:19]}  -->>  {(max_ts or '-')[:19]}")
    print(f"Ortalama Yanıt Süresi: {avg_dur:.1f} ms")

    print("\nDurum Kodları:")
    for s, c in statuses:
        print(f"  HTTP {s}: {c:,} adet")

    print("\nModellere Göre Dağılım:")
    for m, c in models:
        print(f"  {m or 'Bilinmeyen':<25}: {c:,} istek")
    print()


def cmd_export(args):
    target = args.export
    conn = db.get_conn()
    cur = conn.cursor()

    query = "SELECT * FROM request_history"
    params = []
    if args.session:
        query += " WHERE session_id = ?"
        params.append(args.session)
    query += " ORDER BY id ASC"

    cur.execute(query, tuple(params))
    count = 0
    with open(target, "w", encoding="utf-8") as f:
        for row in cur.fetchall():
            d = dict(row)
            for json_col in ("messages_json", "response_json", "usage_json", "prune_info_json"):
                target_key = json_col.replace("_json", "")
                if d.get(json_col):
                    try:
                        d[target_key] = json.loads(d[json_col])
                    except Exception:
                        d[target_key] = d[json_col]
                if json_col in d:
                    del d[json_col]
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
            count += 1

    conn.close()
    print(f"\n[+] {count:,} adet istek başarıyla '{target}' dosyasına aktarıldı.\n")


def cmd_trim(args):
    max_rec = args.trim
    n = db.trim_history(max_records=max_rec)
    print(f"\n[+] İstek geçmişi en son {max_rec:,} kayda kırpıldı. ({n:,} eski kayıt silindi)\n")


def main():
    parser = argparse.ArgumentParser(description="Bayqus Proxy İstek ve Yanıt Analiz Aracı")
    parser.add_argument("--list", action="store_true", help="Son istekleri listele")
    parser.add_argument("--limit", type=int, default=30, help="Listelenecek istek sayısı (varsayılan: 30)")
    parser.add_argument("--offset", type=int, default=0, help="Sayfalama başlangıcı")
    parser.add_argument("--session", type=str, default=None, help="Belirli bir oturumu filtrele")
    parser.add_argument("--search", "-q", type=str, default=None, help="Mesajlar ve yanıtlar içinde ara")
    parser.add_argument("--show", type=int, dest="id", default=None, help="Belirli bir ID'ye sahip isteğin tam detayını göster")
    parser.add_argument("--full", action="store_true", help="Kırpma yapmadan mesajların tam metnini göster")
    parser.add_argument("--stats", action="store_true", help="Genel istatistikleri göster")
    parser.add_argument("--export", type=str, default=None, help="İstek geçmişini JSONL dosyasına aktar")
    parser.add_argument("--trim", type=int, default=None, help="Geçmişi belirtilen boyuta kırp")
    parser.add_argument("--clear", action="store_true", help="Tüm istek geçmişini temizle")

    args = parser.parse_args()

    if args.clear:
        confirm = input("TÜM İSTEK GEÇMİŞİ SİLİNECEK! Emin misiniz? (e/H): ")
        if confirm.strip().lower() in ("e", "y"):
            db.clear_history()
            print("[+] İstek geçmişi tamamen temizlendi.")
        return

    if args.trim is not None:
        cmd_trim(args)
        return

    if args.export:
        cmd_export(args)
        return

    if args.stats:
        cmd_stats(args)
        return

    if args.id is not None:
        cmd_show(args)
        return

    # Varsayılan eylem: listele
    cmd_list(args)


if __name__ == "__main__":
    main()
