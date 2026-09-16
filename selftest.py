"""
Budayiciyi GERCEK transcriptler uzerinde, API'ye hic gitmeden dogrular.

Uc sey kanitlanir:
  1. GECERLILIK — budanmis dizide her tool_result'in oncesinde onu ureten
     tool_use var mi? (API'nin reddettigi tek yapisal hata bu.)
  2. DETERMINIZM — ayni oturum ilerledikce budanmis onek bayt-ozdes kaliyor mu?
     Kalmazsa prompt cache her turda sifirlanir ve budama zarar eder.
  3. KAZANC — gercekte ne kadar bayt/token dusuyor?

Kullanim:  python selftest.py [transcript-sayisi]
"""
import glob
import json
import os
import sys

import pruner

PROJ = os.path.join(os.path.expanduser("~"), ".claude", "projects")


def n(x):
    return f"{x:,}".replace(",", ".")


def load_messages(path):
    """jsonl transcriptten API'ye gidecek messages dizisini kurar."""
    msgs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") not in ("user", "assistant"):
                continue
            m = o.get("message")
            if not isinstance(m, dict) or "role" not in m:
                continue
            c = m.get("content")
            if c is None:
                continue
            msgs.append({"role": m["role"], "content": c})
    return msgs


def validate(messages):
    """tool_use -> tool_result esleismesini denetler. Hata listesi doner."""
    errs = []
    open_ids = set()
    for i, m in enumerate(messages):
        c = m.get("content")
        if not isinstance(c, list):
            continue
        if m.get("role") == "assistant":
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    open_ids.add(b.get("id"))
        else:
            for b in c:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tid = b.get("tool_use_id")
                    if tid not in open_ids:
                        errs.append(f"mesaj[{i}]: sahipsiz tool_result {tid}")
        if not c:
            errs.append(f"mesaj[{i}]: bos icerik")
    return errs


def run_one(path, limit_turns=40):
    full = load_messages(path)
    if len(full) < pruner.MIN_MESSAGES + 8:
        return None

    name = os.path.basename(path)[:8]
    hashes = {}          # cutoff -> prefix_hash  (ayni kesim ayni hash vermeli)
    saved_total = 0
    orig_total = 0
    applied = 0
    errors = []

    # oturumu tur tur ilerlet: her adimda bir mesaj daha ekle
    start = pruner.MIN_MESSAGES
    step = max(1, (len(full) - start) // limit_turns)
    for k in range(start, len(full) + 1, step):
        payload = {"model": "claude-opus-5", "system": "S" * 20000,
                   "messages": full[:k]}
        plan = pruner.plan(payload)
        if not plan.get("applied"):
            continue
        applied += 1
        new_msgs = json.loads(plan["body"].decode("utf-8"))["messages"]

        # ham dilimde ZATEN var olan sorunlari dus: transcript bir agac
        # (subagent sidechain'leri) oldugu icin duz okuma sahipsiz
        # tool_result uretir. Bizi ilgilendiren sadece budamanin EKLEDIGI.
        base = {x.split()[-1] for x in validate(full[:k])}
        e = [x for x in validate(new_msgs) if x.split()[-1] not in base]
        if e:
            errors.extend(f"{name}@{k}: BUDAMA-KAYNAKLI {x}" for x in e[:3])

        cut = plan["cutoff"]
        h = plan["prefix_hash"]
        if cut in hashes and hashes[cut] != h:
            errors.append(f"{name}@{k}: DETERMINIZM kesim={cut} ayni ama onek "
                          f"DEGISTI ({hashes[cut]} -> {h}) — cache kirilir")
        hashes[cut] = h

        ob = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        nb = len(plan["body"])
        orig_total += ob
        saved_total += ob - nb

    if not applied:
        return None
    return {"name": name, "turns": applied, "messages": len(full),
            "orig": orig_total, "saved": saved_total,
            "cutoffs": len(hashes), "errors": errors}


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    files = sorted(glob.glob(os.path.join(PROJ, "*", "*.jsonl")),
                   key=os.path.getsize, reverse=True)[:want * 3]

    rows, all_errors = [], []
    for p in files:
        pruner._SESSIONS.clear()
        try:
            r = run_one(p)
        except Exception as ex:
            all_errors.append(f"{os.path.basename(p)[:8]}: {type(ex).__name__}: {ex}")
            continue
        if r:
            rows.append(r)
            all_errors.extend(r["errors"])
        if len(rows) >= want:
            break

    print(f"{'transcript':<12}{'mesaj':>8}{'tur':>6}{'kesim':>7}"
          f"{'orijinal':>14}{'kazanc':>14}{'%':>7}")
    print("-" * 68)
    to, ts = 0, 0
    for r in rows:
        pct = r["saved"] / r["orig"] * 100 if r["orig"] else 0
        to += r["orig"]
        ts += r["saved"]
        print(f"{r['name']:<12}{n(r['messages']):>8}{r['turns']:>6}"
              f"{r['cutoffs']:>7}{n(r['orig']):>14}{n(r['saved']):>14}{pct:>6.1f}%")
    print("-" * 68)
    if to:
        print(f"{'TOPLAM':<12}{'':>8}{'':>6}{'':>7}{n(to):>14}{n(ts):>14}"
              f"{ts / to * 100:>6.1f}%")
        print(f"\nkabaca ~{n(ts // 4)} token dusuruldu "
              f"({len(rows)} transcript, orneklenmis turlar)")

    print()
    if all_errors:
        print(f"!!! {len(all_errors)} SORUN:")
        for e in all_errors[:20]:
            print(f"    {e}")
    else:
        print("GECERLILIK: tum budanmis diziler saglam "
              "(sahipsiz tool_result yok, bos icerik yok)")
        print("DETERMINIZM: ayni kesim her zaman ayni onek hash'i uretti")


if __name__ == "__main__":
    main()
