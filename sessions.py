"""
Oturum kaydi ve oturum bazli rota sabitleme (pin).

Claude Code her istege `x-claude-code-session-id` basligini koyar; bu kimlik
sohbet boyunca sabittir ve MODEL DEGISSE BILE degismez (kayitli trafikte
tek bir oturumun opus-4-7 / sonnet-5 arasinda gezdigi gorulmustur). Yani
"bu sohbet gateway'e gitsin, su sohbet abonelige" demek mumkundur.

Ayni kimlik ~/.claude/projects/<proje>/<kimlik>.jsonl dosyasinin adidir;
buradan sohbetin hangi projede acildigi okunabilir ve panoda ham hex yerine
proje adi gosterilir.

Iki seviye sabitleme var, logs/sessions.json'a yazilir ve proxy yeniden
baslasa da kalir:
  * oturum sabitlemesi — yalnizca o sohbet icin. Yeni sohbette kimlik
    degistigi icin sifirlanir.
  * proje kurali       — o klasorde acilan HER sohbet icin. Kalicidir.
Oncelik: oturum > proje > model eslesmesi.
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "logs", "sessions.json")
PROJECTS = os.path.join(os.path.expanduser("~"), ".claude", "projects")
CLAUDE_SESSIONS_DIR = os.path.expandvars(r"%APPDATA%\Claude\claude-code-sessions")

_LOCK = threading.Lock()
_PINS = {}                # session_id -> rota adi
_PROJ_PINS = {}           # proje yolu (kucuk harf) -> rota adi
_GROUP_PINS = {}          # grup adi -> rota adi
_SUBAGENT_PINS = {}       # session_id -> subagent rota adi
_GROUP_SUBAGENT_PINS = {} # grup adi -> subagent rota adi
_SEEN = {}                # session_id -> {ilk, son, istek, modeller{}, rota, proje, agent_id, parent}
_PROJECT = {}             # session_id -> proje etiketi ("" = bulunamadi)
_AGENT_PARENT = {}        # agent_id / subagent_sid -> parent_session_id
_AGENT_META = {}          # agent_id -> metadata (dict)
_CLAUDE_META_CACHE = {}
_CLAUDE_META_TIME = 0


# --------------------------------------------------------------------------
# kalici durum
# --------------------------------------------------------------------------
def load():
    global _PINS, _PROJ_PINS, _GROUP_PINS, _SUBAGENT_PINS, _GROUP_SUBAGENT_PINS
    try:
        with open(STATE, encoding="utf-8") as f:
            d = json.load(f)
        _PINS = {str(k): str(v) for k, v in (d.get("pins") or {}).items() if v}
        _PROJ_PINS = {str(k).lower(): str(v)
                      for k, v in (d.get("projects") or {}).items() if v}
        _GROUP_PINS = {str(k): str(v) for k, v in (d.get("groups") or {}).items() if v}
        _SUBAGENT_PINS = {str(k): str(v) for k, v in (d.get("subagent_pins") or {}).items() if v}
        _GROUP_SUBAGENT_PINS = {str(k): str(v) for k, v in (d.get("group_subagents") or {}).items() if v}
    except FileNotFoundError:
        _PINS, _PROJ_PINS, _GROUP_PINS, _SUBAGENT_PINS, _GROUP_SUBAGENT_PINS = {}, {}, {}, {}, {}
    except Exception as e:
        print(f"!!! sessions.json okunamadi ({type(e).__name__}: {e}) — "
              f"sabitlemeler bos baslatildi")
        _PINS, _PROJ_PINS, _GROUP_PINS, _SUBAGENT_PINS, _GROUP_SUBAGENT_PINS = {}, {}, {}, {}, {}
    return _PINS, _PROJ_PINS


def _save_locked():
    tmp = STATE + ".tmp"
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({
            "pins": _PINS,
            "projects": _PROJ_PINS,
            "groups": _GROUP_PINS,
            "subagent_pins": _SUBAGENT_PINS,
            "group_subagents": _GROUP_SUBAGENT_PINS,
        }, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE)


# --------------------------------------------------------------------------
# proje cozumleme & alt-ajan eslestirme
# --------------------------------------------------------------------------
def _decode_project(dirname):
    """`C--workspace-myproject` -> `C:/workspace/myproject`."""
    s = dirname
    if len(s) > 3 and s[1:3] == "--":
        s = s[0] + ":/" + s[3:]
        kok, kalan = s[:3], s[3:]
    else:
        return s.replace("-", "/")

    parcalar = kalan.split("-")
    yol = kok
    cikti = [kok.rstrip("/")]
    i = 0
    try:
        while i < len(parcalar):
            for j in range(len(parcalar), i, -1):
                aday = "-".join(parcalar[i:j])
                if os.path.isdir(os.path.join(yol, aday)):
                    yol = os.path.join(yol, aday)
                    cikti.append(aday)
                    i = j
                    break
            else:
                cikti.extend(parcalar[i:])
                break
    except Exception:
        return s.replace("-", "/")
    return "/".join(cikti)


def record_agent(sid, agent_id):
    """Alt-ajan ile ana oturumu iliskilendirir."""
    if sid and agent_id:
        with _LOCK:
            _AGENT_PARENT[agent_id] = sid


def parent_session_for(sid, agent_id=None):
    """Alt-ajanin bagli oldugu ana oturumu doner."""
    with _LOCK:
        if agent_id and agent_id in _AGENT_PARENT:
            return _AGENT_PARENT[agent_id]
        if sid and sid in _AGENT_PARENT:
            return _AGENT_PARENT[sid]
    # Dosya sisteminden tarayip bulmaya calis
    project_for(sid, agent_id)
    with _LOCK:
        if agent_id and agent_id in _AGENT_PARENT:
            return _AGENT_PARENT[agent_id]
        if sid and sid in _AGENT_PARENT:
            return _AGENT_PARENT[sid]
    return None


def project_for(sid, agent_id=None):
    """Oturumun veya alt-ajanin acildigi proje etiketi."""
    if not sid and not agent_id:
        return ""

    with _LOCK:
        # 1) Eger agent_id ana oturuma bagliysa ana oturumun projesini kullan
        if agent_id and agent_id in _AGENT_PARENT:
            parent = _AGENT_PARENT[agent_id]
            if parent in _PROJECT:
                return _PROJECT[parent]

        # 2) Onbellek kontrolu
        if sid and sid in _PROJECT:
            return _PROJECT[sid]
        if agent_id and agent_id in _PROJECT:
            return _PROJECT[agent_id]

    label = ""
    target_ids = [x for x in (sid, agent_id) if x]

    try:
        if os.path.isdir(PROJECTS):
            for d in os.listdir(PROJECTS):
                pdir = os.path.join(PROJECTS, d)
                if not os.path.isdir(pdir):
                    continue

                # A) Ana oturum dosyasi: <d>/<sid>.jsonl
                for tid in target_ids:
                    if os.path.exists(os.path.join(pdir, tid + ".jsonl")):
                        label = _decode_project(d)
                        break
                if label:
                    break

                # B) Alt-ajan dosyasi: <d>/<parent>/subagents/agent-<tid>.jsonl
                for parent_dir in os.listdir(pdir):
                    sub_path = os.path.join(pdir, parent_dir, "subagents")
                    if os.path.isdir(sub_path):
                        for tid in target_ids:
                            c1 = os.path.join(sub_path, f"agent-{tid}.jsonl")
                            c2 = os.path.join(sub_path, f"{tid}.jsonl")
                            matched = c1 if os.path.exists(c1) else (c2 if os.path.exists(c2) else None)
                            if matched:
                                label = _decode_project(d)
                                with _LOCK:
                                    for x in target_ids:
                                        _AGENT_PARENT[x] = parent_dir
                                break
                    if label:
                        break
                if label:
                    break
    except Exception:
        label = ""

    with _LOCK:
        for tid in target_ids:
            if label or _SEEN.get(tid, {}).get("istek", 0) > 5:
                _PROJECT[tid] = label
    return label


# --------------------------------------------------------------------------
# kayit & sabitleme
# --------------------------------------------------------------------------
def note(sid, model=None, route=None, agent_id=None):
    """Oturumu / alt-ajani gorulmus isaretler."""
    if not sid and not agent_id:
        return
    now = time.time()
    with _LOCK:
        if sid and agent_id:
            _AGENT_PARENT[agent_id] = sid
        target_id = sid or agent_id
        parent = _AGENT_PARENT.get(agent_id or sid)
        st = _SEEN.setdefault(target_id, {
            "ilk": now, "son": now, "istek": 0,
            "modeller": {}, "rota": None,
            "agent_id": agent_id, "parent": parent
        })
        st["son"] = now
        st["istek"] += 1
        if agent_id:
            st["agent_id"] = agent_id
        if parent:
            st["parent"] = parent
        if model:
            st["modeller"][model] = st["modeller"].get(model, 0) + 1
        if route:
            st["rota"] = route


def load_claude_desktop_metadata():
    """Claude Desktop'un %APPDATA%/Claude/claude-code-sessions altindaki oturumlarini okur ve onbellege alir."""
    global _CLAUDE_META_CACHE, _CLAUDE_META_TIME
    now = time.time()
    if _CLAUDE_META_CACHE and (now - _CLAUDE_META_TIME < 3):
        return dict(_CLAUDE_META_CACHE)

    known_groups = []
    if os.path.isdir(CLAUDE_SESSIONS_DIR):
        import glob
        pattern = os.path.join(CLAUDE_SESSIONS_DIR, "**", "local_*.json")
        for f in glob.glob(pattern, recursive=True):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    d = json.load(fp)
                cid = d.get("cliSessionId")
                if not cid:
                    continue
                title = (d.get("title") or "").strip() or "İsimsiz Sohbet"
                matched_g = None
                for kg in known_groups:
                    if title.lower().startswith(kg.lower()):
                        matched_g = kg
                        break
                if not matched_g:
                    parts = title.split()
                    matched_g = parts[0] if parts else "Genel"
                
                res[cid] = {
                    "local_id": d.get("sessionId"),
                    "cli_id": cid,
                    "title": title,
                    "group": matched_g,
                    "cwd": d.get("cwd") or "",
                    "origin_cwd": d.get("originCwd") or "",
                    "archived": bool(d.get("isArchived", False)),
                    "last_focused": d.get("lastFocusedAt", 0)
                }
            except Exception:
                pass

    with _LOCK:
        _CLAUDE_META_CACHE = res
        _CLAUDE_META_TIME = now
    return dict(res)


def pinned(sid, agent_id=None):
    """(rota_adi, kaynak) doner.
    Oncelik sirasi:
      1) Eger alt-ajan ise (agent_id veya sid bir alt-ajan):
         - Ana oturumunun ozel alt-ajan ayari var mi? (_SUBAGENT_PINS)
         - Ana oturumun grubunun alt-ajan ayari var mi? (_GROUP_SUBAGENT_PINS)
         - Yoksa ana oturumun kendi rotasini devral!
      2) Oturum dogrudan sabitlenmis mi? (_PINS[sid])
      3) Oturumun bagli oldugu Claude Desktop grubu sabitlenmis mi? (_GROUP_PINS[group])
      4) Proje kurali var mi? (_PROJ_PINS[proje])
      5) Hicbiri yoksa (None, None) -> Varsayilan (default) rotaya duser.
    """
    sid = sid or ""
    meta = load_claude_desktop_metadata()
    parent = parent_session_for(sid, agent_id)

    # 1. Alt-ajan kontrolu
    if parent or agent_id:
        p_sid = parent or sid
        # Ana oturumun ozel alt-ajan ayari
        if p_sid in _SUBAGENT_PINS and _SUBAGENT_PINS[p_sid]:
            return _SUBAGENT_PINS[p_sid], "alt-ajan (sohbet kuralı)"
        # Ana oturumun grubunun alt-ajan ayari
        p_info = meta.get(p_sid, {})
        p_group = p_info.get("group")
        if p_group and p_group in _GROUP_SUBAGENT_PINS and _GROUP_SUBAGENT_PINS[p_group]:
            return _GROUP_SUBAGENT_PINS[p_group], f"alt-ajan (grup: {p_group})"
        # Ana oturumun rotasini devral
        if p_sid:
            p_route, p_src = pinned(p_sid)
            if p_route:
                return p_route, f"ana oturumdan miras ({p_src})"

    # Alt-ajan dogrudan sabitlenmis mi?
    if agent_id and agent_id in _PINS:
        return _PINS[agent_id], "altajan"

    # 2. Oturum dogrudan sabitlenmis mi?
    r = _PINS.get(sid)
    if r:
        return r, "oturum"

    # 3. Claude Desktop Grubu kurali
    s_info = meta.get(sid, {})
    gname = s_info.get("group")
    if gname and gname in _GROUP_PINS and _GROUP_PINS[gname]:
        return _GROUP_PINS[gname], f"grup ({gname})"

    # 4. Proje klasor kurali
    proje = project_for(sid, agent_id)
    if proje:
        r = _PROJ_PINS.get(proje.lower())
        if r:
            return r, "proje klasörü"

    return None, None


def pin_group(group_name, route_name):
    """Grup kurali. route_name bos ise kural silinir."""
    g = (group_name or "").strip()
    if not g:
        return False, "grup adi bos"
    with _LOCK:
        if route_name:
            _GROUP_PINS[g] = route_name
            msg = f"{g} grubu -> {route_name}"
        else:
            _GROUP_PINS.pop(g, None)
            msg = f"{g} grubu kurali kaldirildi"
        try:
            _save_locked()
        except Exception as e:
            return True, f"{msg} (DISKE YAZILAMADI: {type(e).__name__}: {e})"
    return True, msg


def pin_group_subagent(group_name, route_name):
    """Grubun alt-ajanlari icin kural."""
    g = (group_name or "").strip()
    if not g:
        return False, "grup adi bos"
    with _LOCK:
        if route_name:
            _GROUP_SUBAGENT_PINS[g] = route_name
            msg = f"{g} grubu alt-ajanlari -> {route_name}"
        else:
            _GROUP_SUBAGENT_PINS.pop(g, None)
            msg = f"{g} grubu alt-ajan kurali kaldirildi (ana sohbete devredildi)"
        try:
            _save_locked()
        except Exception as e:
            return True, f"{msg} (DISKE YAZILAMADI: {type(e).__name__}: {e})"
    return True, msg


def pin_subagent(sid, route_name):
    """Tek bir sohbetin alt-ajanlari icin ozel rota sabitleme."""
    sid = (sid or "").strip()
    if not sid:
        return False, "oturum kimligi bos"
    with _LOCK:
        if route_name:
            _SUBAGENT_PINS[sid] = route_name
            msg = f"{sid[:8]} alt-ajanlari -> {route_name}"
        else:
            _SUBAGENT_PINS.pop(sid, None)
            msg = f"{sid[:8]} alt-ajan kurali kaldirildi (ana sohbete devredildi)"
        try:
            _save_locked()
        except Exception as e:
            return True, f"{msg} (DISKE YAZILAMADI: {type(e).__name__}: {e})"
    return True, msg


def group_pins():
    return dict(_GROUP_PINS)


def subagent_pins():
    return dict(_SUBAGENT_PINS)


def group_subagent_pins():
    return dict(_GROUP_SUBAGENT_PINS)


def pin_project(proje, route_name):
    """Klasor kurali. route_name bos ise kural silinir."""
    key = (proje or "").strip().lower()
    if not key:
        return False, "proje yolu bos"
    with _LOCK:
        if route_name:
            _PROJ_PINS[key] = route_name
            msg = f"{proje} -> {route_name} (tum sohbetler)"
        else:
            if key not in _PROJ_PINS:
                return False, f"{proje} zaten kuralsiz"
            _PROJ_PINS.pop(key, None)
            msg = f"{proje} kurali kaldirildi"
        try:
            _save_locked()
        except Exception as e:
            return True, f"{msg} (DISKE YAZILAMADI: {type(e).__name__}: {e})"
    return True, msg


def project_pins():
    return dict(_PROJ_PINS)


def list_all_projects():
    """~/.claude/projects/ altindaki tum projeleri bulur ve doner."""
    projs = set()
    try:
        if os.path.isdir(PROJECTS):
            for d in os.listdir(PROJECTS):
                if os.path.isdir(os.path.join(PROJECTS, d)):
                    dec = _decode_project(d)
                    if dec:
                        projs.add(dec)
    except Exception:
        pass
    with _LOCK:
        for p in _PROJ_PINS.keys():
            projs.add(p)
        for st in _SEEN.values():
            if st.get("proje"):
                projs.add(st["proje"])
    return sorted(list(projs), key=str.lower)


def pin(sid, route_name):
    """route_name bos/None ise sabitleme kaldirilir. (degisti_mi, mesaj) doner."""
    sid = (sid or "").strip()
    if not sid:
        return False, "oturum kimligi bos"
    with _LOCK:
        if route_name:
            _PINS[sid] = route_name
            msg = f"{sid} -> {route_name}"
        else:
            if sid not in _PINS:
                return False, f"{sid} zaten sabit degil"
            _PINS.pop(sid, None)
            msg = f"{sid} sabitlemesi kaldirildi"
        try:
            _save_locked()
        except Exception as e:
            return True, f"{msg} (DISKE YAZILAMADI: {type(e).__name__}: {e})"
    return True, msg


def get_claude_desktop_groups_data(default_route="gateway"):
    """Claude Desktop sol panelindeki gruplar ve sohbetleri hiyerarsik olarak doner."""
    meta = load_claude_desktop_metadata()
    grouped = {}
    for cid, sinfo in meta.items():
        if sinfo.get("archived"):
            continue
        gname = sinfo.get("group") or "Genel"
        grouped.setdefault(gname, []).append(sinfo)

    out = []
    for gname in sorted(grouped.keys()):
        slist = grouped[gname]
        g_sabit = _GROUP_PINS.get(gname)
        g_sub_sabit = _GROUP_SUBAGENT_PINS.get(gname)
        g_etkin = g_sabit or default_route
        g_sub_etkin = g_sub_sabit or g_etkin

        sessions_out = []
        for s in sorted(slist, key=lambda x: x.get("last_focused", 0), reverse=True):
            cid = s["cli_id"]
            s_sabit = _PINS.get(cid)
            etkin, kaynak = pinned(cid)
            if not etkin:
                etkin = default_route
                kaynak = "varsayılan"

            sub_sabit = _SUBAGENT_PINS.get(cid)
            if sub_sabit:
                sub_etkin = sub_sabit
                sub_kaynak = "özel kural"
            elif g_sub_sabit:
                sub_etkin = g_sub_sabit
                sub_kaynak = f"grup kuralı ({gname})"
            else:
                sub_etkin = etkin
                sub_kaynak = f"ana sohbetten ({etkin})"

            seen_info = _SEEN.get(cid, {})
            last_seen = seen_info.get("son")
            yas_sn = int(time.time() - last_seen) if last_seen else None

            sessions_out.append({
                "id": cid,
                "kisa": cid[:8],
                "title": s["title"],
                "cwd": s["origin_cwd"] or s["cwd"],
                "sabit": s_sabit,
                "etkin": etkin,
                "kaynak": kaynak,
                "subagent_sabit": sub_sabit,
                "subagent_etkin": sub_etkin,
                "subagent_kaynak": sub_kaynak,
                "istek": seen_info.get("istek", 0),
                "yas_sn": yas_sn,
            })

        out.append({
            "name": gname,
            "sabit": g_sabit,
            "etkin": g_etkin,
            "subagent_sabit": g_sub_sabit,
            "subagent_etkin": g_sub_etkin,
            "sessions": sessions_out
        })
    return out


def snapshot(limit=40):
    """Pano icin oturum listesi; en son gorulen basta.
    Kullanici istegi: Gecici alt-ajanlar ana tabloda kalabalik yapmaz;
    yalnizca ana sohbetler listelenir.
    """
    meta = load_claude_desktop_metadata()
    with _LOCK:
        items = list(_SEEN.items())
    out = []
    for sid, st in items:
        # Alt-ajanlari filtrele (gecici olduklari icin ana listede yer almazlar)
        if st.get("agent_id") or st.get("parent"):
            continue

        mods = sorted(st["modeller"].items(), key=lambda kv: -kv[1])
        s_meta = meta.get(sid, {})
        title = s_meta.get("title") or sid[:8]
        group = s_meta.get("group") or ""
        sabit, kaynak = pinned(sid)
        sub_sabit = _SUBAGENT_PINS.get(sid)

        out.append({
            "id": sid,
            "kisa": sid[:8],
            "title": title,
            "group": group,
            "proje": s_meta.get("origin_cwd") or project_for(sid),
            "istek": st["istek"],
            "modeller": [m for m, _ in mods[:3]],
            "rota": st["rota"],
            "sabit": _PINS.get(sid),
            "etkin": sabit,
            "kaynak": kaynak,
            "subagent_sabit": sub_sabit,
            "yas_sn": int(time.time() - st["son"]),
        })
    out.sort(key=lambda r: (r["yas_sn"] if r["yas_sn"] is not None else 999999))
    bilinen = {r["id"] for r in out}
    for sid, rota in _PINS.items():
        if sid not in bilinen:
            s_meta = meta.get(sid, {})
            out.append({"id": sid, "kisa": sid[:8],
                        "title": s_meta.get("title") or sid[:8],
                        "group": s_meta.get("group") or "",
                        "proje": s_meta.get("origin_cwd") or project_for(sid),
                        "istek": 0, "modeller": [], "rota": None,
                        "sabit": rota, "etkin": rota, "kaynak": "oturum",
                        "subagent_sabit": _SUBAGENT_PINS.get(sid),
                        "yas_sn": None})
    return out[:limit]
