"""
Model bazli yonlendirme + kimlik bilgisi yalitimi.

Amac: tek port, birden cok saglayici. Ornegin
    opus*    -> api.anthropic.com   (abonelik OAuth, aynen gecer)
    sonnet*  -> custom-gateway...  (gateway anahtari, OAuth ASLA gitmez)

GUVENLIK — bu dosyanin asil isi:
Abonelik OAuth token'i `Authorization: Bearer` ile gelir ve SADECE
api.anthropic.com'a aittir. Baska bir upstream'e iletilirse token sizar.
Bu yuzden:
  * "passthrough" kimligi yalnizca SUBSCRIPTION_HOSTS icin gecerlidir;
    baska bir host icin yapilandirilirsa proxy ACILMAZ.
  * passthrough disindaki her rotada gelen Authorization / x-api-key
    basliklari DUSURULUR, yerine rotanin kendi anahtari konur.
"""
import json
import os
import threading
from urllib.parse import urlparse

# Abonelik OAuth'unun gitmesine izin verilen tek yer.
SUBSCRIPTION_HOSTS = {"api.anthropic.com"}

# Rotanin kendi kimligiyle degistirilecek basliklar.
CREDENTIAL_HEADERS = {"authorization", "x-api-key", "api-key"}

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "routes.json")

_KEYCACHE = {}
_CACHED_CONFIG = None
_CACHED_MTIME = 0
_CONFIG_LOCK = threading.Lock()


def resolve_key(auth, with_source=False):
    """Rotanin anahtarini cozer. Iki kaynak:
        env:  os.environ[auth["env"]]
        file: auth["file"] JSON dosyasindan auth["json_key"] alani

    Dosya kaynagi, anahtarin hicbir yere yapistirilmasina gerek birakmaz.
    Deger asla loglanmaz; yalnizca uzunlugu bildirilir.
    """
    def done(val, src):
        return (val, src) if with_source else val

    if auth.get("env"):
        v = os.environ.get(auth["env"], "")
        if v:
            return done(v, "env:" + auth["env"])
    path = auth.get("file")
    if not path:
        return done("", "yok")
    try:
        st = os.stat(path)
        sig = (st.st_mtime_ns, st.st_size)
        hit = _KEYCACHE.get(path)
        if hit and hit[0] == sig:
            return done(hit[1], "dosya:" + os.path.basename(path))
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        val = str(data.get(auth.get("json_key", ""), "") or "")
        _KEYCACHE[path] = (sig, val)
        return done(val, "dosya:" + os.path.basename(path))
    except Exception:
        return done("", "dosya-okunamadi")

DEFAULT_CONFIG = {
    "default": {
        "name": "anthropic",
        "upstream": os.environ.get("BAYQUS_UPSTREAM_URL", "https://api.anthropic.com"),
        "auth": {
            "header": "x-api-key",
            "env": "ANTHROPIC_API_KEY",
        },
        "prune": True,
    },
    "routes": [],
}


class RouteError(Exception):
    pass


def load(path=CONFIG):
    if not os.path.exists(path):
        return dict(DEFAULT_CONFIG)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("default", DEFAULT_CONFIG["default"])
    cfg.setdefault("routes", [])
    return cfg


def get_config(path=CONFIG):
    """Mtime bazli dinamik yukleme. Dosya degisince proxy'yi yeniden baslatmaya gerek kalmaz."""
    global _CACHED_CONFIG, _CACHED_MTIME
    with _CONFIG_LOCK:
        try:
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0
            if _CACHED_CONFIG is None or mtime > _CACHED_MTIME:
                _CACHED_CONFIG = load(path)
                _CACHED_MTIME = mtime
        except Exception:
            if _CACHED_CONFIG is None:
                _CACHED_CONFIG = DEFAULT_CONFIG
        return _CACHED_CONFIG


def save_config(cfg, path=CONFIG):
    """Yapilandirmayi dogrular ve routes.json'a atomik olarak yazar."""
    global _CACHED_CONFIG, _CACHED_MTIME
    problems = validate(cfg)
    if problems:
        return False, "; ".join(problems)

    with _CONFIG_LOCK:
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            _CACHED_CONFIG = cfg
            _CACHED_MTIME = os.path.getmtime(path)
            return True, "Yapılandırma başarıyla kaydedildi ve uygulandı."
        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            return False, f"Kaydetme hatası: {e}"


def toggle_route(name, enabled, path=CONFIG):
    """Tek bir rotayi aninda acar/kapatir."""
    cfg = get_config(path)
    found = False
    for r in cfg.get("routes", []):
        if r.get("name") == name:
            r["enabled"] = bool(enabled)
            found = True
            break
    if not found:
        return False, f"Rota bulunamadı: {name}"
    return save_config(cfg, path)


def save_route(route_data, path=CONFIG):
    """Bir rotayi ekler veya var olanini gunceller."""
    name = (route_data.get("name") or "").strip()
    if not name:
        return False, "Rota adı boş olamaz."
    cfg = get_config(path)
    routes = cfg.setdefault("routes", [])
    idx = -1
    for i, r in enumerate(routes):
        if r.get("name") == name:
            idx = i
            break
    if idx >= 0:
        routes[idx] = route_data
    else:
        routes.append(route_data)
    return save_config(cfg, path)


def delete_route(name, path=CONFIG):
    """Bir rotayi siler."""
    cfg = get_config(path)
    routes = cfg.get("routes", [])
    new_routes = [r for r in routes if r.get("name") != name]
    if len(new_routes) == len(routes):
        return False, f"Rota bulunamadı: {name}"
    cfg["routes"] = new_routes
    return save_config(cfg, path)


def set_default_route(name, path=CONFIG):
    """Varsayilan (fallback) rotayi degistirir."""
    name = (name or "").strip()
    cfg = get_config(path)
    target = None
    for r in cfg.get("routes", []):
        if r.get("name") == name:
            target = dict(r)
            break
    if not target:
        return False, f"Rota bulunamadı: {name}"
    target.pop("enabled", None)
    target.pop("model_contains", None)
    cfg["default"] = target
    return save_config(cfg, path)


def _host(url):
    return (urlparse(url).hostname or "").lower()


def enabled_routes(cfg):
    """Sadece acik rotalar. 'enabled': false olan hicbir sekilde eslesmez."""
    return [r for r in cfg["routes"] if r.get("enabled", True)]


def validate(cfg):
    """Yapilandirmayi acilista denetler. Sorun listesi doner; bos degilse acma."""
    problems = []
    for r in enabled_routes(cfg) + [cfg["default"]]:
        name = r.get("name", "?")
        up = r.get("upstream")
        if not up:
            problems.append(f"[{name}] upstream yok")
            continue
        auth = r.get("auth")
        if auth == "passthrough":
            if _host(up) not in SUBSCRIPTION_HOSTS:
                problems.append(
                    f"[{name}] auth=passthrough ama upstream={_host(up)} — "
                    f"abonelik OAuth'u yalnizca {sorted(SUBSCRIPTION_HOSTS)} "
                    f"icin iletilebilir. 'auth' alanini bir anahtarla degistirin."
                )
        elif auth == "strip":
            pass
        elif isinstance(auth, dict):
            if not auth.get("header"):
                problems.append(f"[{name}] auth.header eksik")
            if not auth.get("env") and not auth.get("file"):
                problems.append(f"[{name}] auth.env veya auth.file gerekli")
            elif not resolve_key(auth):
                src = auth.get("env") or auth.get("file")
                problems.append(
                    f"[{name}] anahtar cozulemedi ({src}) — bu rota kimliksiz kalir")
        else:
            problems.append(f"[{name}] gecersiz auth: {auth!r}")
    return problems


def by_name(cfg):
    """ad -> rota. default dahil, yalnizca acik olanlar."""
    d = {r["name"]: r for r in enabled_routes(cfg)}
    d[cfg["default"]["name"]] = cfg["default"]
    return d


def pick(cfg, model, pin=None):
    """Rota secer. Oncelik: oturum sabitlemesi > model eslesmesi > default.

    `pin` bir rota adidir (oturum bazli sabitleme). Bilinmeyen veya kapatilmis
    bir ada isaret ediyorsa sessizce yok sayilmaz — cagiran taraf farki
    gorsun diye ikinci deger olarak bildirilir.
    Doner: (rota, sabit_uygulandi_mi, uyari_veya_None)
    """
    if pin:
        r = by_name(cfg).get(pin)
        if r is not None:
            return r, True, None
        uyari = f"sabitlenen rota yok/kapali: {pin} — model eslesmesine dusuldu"
    else:
        uyari = None

    m = (model or "").lower()
    for r in enabled_routes(cfg):
        for frag in r.get("model_contains") or []:
            if frag.lower() in m:
                return r, False, uyari
    return cfg["default"], False, uyari


def rewrite_model(route, parsed):
    """Rotanin model_rewrite'ini uygular. parsed'i YERINDE degistirir.

    Model secicisini backend anahtari olarak kullanmayi mumkun kilar:
    arayuzde Fable secilir, govdeye Opus yazilir, istek abonelige gider.
    Doner: (eski_ad, yeni_ad) veya None.
    """
    target = route.get("model_rewrite")
    if not target or not isinstance(parsed, dict):
        return None
    old = parsed.get("model")
    if old == target:
        return None
    parsed["model"] = target
    return (old, target)


def build_headers(incoming, route):
    """Upstream'e gidecek basliklari kurar.

    `incoming` zaten hop-by-hop'tan arindirilmis olmali.
    Doner: (basliklar, kimlik_etiketi) — etiket loglama icin, deger ASLA degil.
    """
    auth = route.get("auth")

    if auth == "passthrough":
        if _host(route["upstream"]) not in SUBSCRIPTION_HOSTS:
            # validate() bunu acilista yakalar; burasi ikinci savunma hatti.
            raise RouteError(
                f"passthrough {route['upstream']} icin reddedildi — OAuth sizabilirdi"
            )
        got = incoming.get("Authorization") or incoming.get("authorization")
        return dict(incoming), (got.split(" ", 1)[0] if got else "YOK")

    # Buradan sonrasi: gelen kimlik bilgileri DUSER.
    out = {k: v for k, v in incoming.items()
           if k.lower() not in CREDENTIAL_HEADERS}

    if auth == "strip":
        return out, "strip"

    key, ksrc = resolve_key(auth, with_source=True)
    if key:
        out[auth["header"]] = auth.get("prefix", "") + key
    for k, v in (auth.get("extra_headers") or {}).items():
        out[k] = v
    return out, f"{auth['header']}<-{ksrc}({len(key)})"
