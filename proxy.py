"""
bayqus-proxy — Faz 2: budama + olcum.

Claude Code'u (abonelik OAuth) yerel proxy uzerinden api.anthropic.com'a
baglar, istek govdesini budar ve her turu olcer.

Kullanim:
    python proxy.py
    # baska bir kabukta:
    $env:ANTHROPIC_BASE_URL = "http://127.0.0.1:5199"
    claude -p "..."

Modlar (BAYQUS_MODE):
    prune        budar ve budanmisi gonderir           (varsayilan)
    shadow       budamayi hesaplar, ORIJINALI gonderir (risksiz olcum)
    passthrough  budama yok, sadece olcum

Tasarim notlari:
  * Basliklar `host` / `content-length` / `accept-encoding` haric AYNEN iletilir.
    Authorization: Bearer <oauth> dokunulmadan gecer — abonelik bu sayede calisir.
  * accept-encoding dusuruluyor ki upstream sikistirmasiz donsun ve SSE
    okunabilsin (urllib gzip'i kendi acmaz).
  * SSE tamponlanmaz: chunked olarak aninda akitilir, es zamanli olarak
    usage alanlari icin ayristirilir.
  * TLS dogrulamasi ACIK. Bu proxy gercek OAuth token tasiyor.
  * /v1/messages/count_tokens budanmaz — budarsak CLI'nin compaction karari
    gercekle uyusmaz. Oldugu gibi gecer (hafif fazla tahmin eder, guvenli yon).
"""
import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import ssl
import json
import os
import sys
import time
import shutil
import threading
from datetime import datetime

import agent_bridge
import dashboard
import db
import mcp_manager
import mocks
import pruner
import router
import sessions
import stats
import tiktoken

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

ROUTES = router.load()
# Tek upstream'i zorlamak icin BAYQUS_UPSTREAM hala kullanilabilir (yonlendirmeyi ezer).
FORCE_UPSTREAM = os.environ.get("BAYQUS_UPSTREAM")
PORT = int(os.environ.get("BAYQUS_PORT", "5199"))
MODE = os.environ.get("BAYQUS_MODE", "prune").lower()
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
METRICS = os.path.join(LOG_DIR, "metrics.jsonl")

SSL_CTX = ssl.create_default_context()          # dogrulama ACIK

HOP_BY_HOP = {"host", "content-length", "accept-encoding", "connection",
              "keep-alive", "proxy-connection", "transfer-encoding", "te", "upgrade"}


def n(x):
    return f"{x:,}".replace(",", ".")


_tiktoken_enc = None
def count_tokens_locally(body_bytes):
    global _tiktoken_enc
    if _tiktoken_enc is None:
        try:
            _tiktoken_enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_enc = False

    if _tiktoken_enc is False or not body_bytes:
        return max(1, len(body_bytes or b"") // 4)

    try:
        data = json.loads(body_bytes.decode("utf-8") if isinstance(body_bytes, bytes) else str(body_bytes))
        total_tokens = 0
        enc = _tiktoken_enc

        system = data.get("system")
        if isinstance(system, str):
            total_tokens += len(enc.encode(system))
        elif isinstance(system, list):
            for block in system:
                if isinstance(block, dict):
                    total_tokens += len(enc.encode(block.get("text", "")))
                elif isinstance(block, str):
                    total_tokens += len(enc.encode(block))

        tools = data.get("tools", [])
        if tools:
            tools_json = json.dumps(tools, ensure_ascii=False)
            total_tokens += len(enc.encode(tools_json))

        messages = data.get("messages", [])
        for msg in messages:
            total_tokens += 3
            content = msg.get("content", "")
            if isinstance(content, str):
                total_tokens += len(enc.encode(content))
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict):
                        btype = b.get("type", "")
                        if btype == "text":
                            total_tokens += len(enc.encode(b.get("text", "")))
                        elif btype == "tool_use":
                            total_tokens += len(enc.encode(b.get("name", "")))
                            inp = b.get("input")
                            if inp:
                                total_tokens += len(enc.encode(json.dumps(inp, ensure_ascii=False)))
                        elif btype == "tool_result":
                            res_c = b.get("content", "")
                            if isinstance(res_c, str):
                                total_tokens += len(enc.encode(res_c))
                            else:
                                total_tokens += len(enc.encode(json.dumps(res_c, ensure_ascii=False)))
                        elif btype == "image":
                            total_tokens += 1600
                    elif isinstance(b, str):
                        total_tokens += len(enc.encode(b))

        return max(1, total_tokens)
    except Exception:
        return max(1, len(body_bytes) // 4)



def analyze_request(body):
    """Istek govdesinden olcum cikarir. Govdeyi DEGISTIRMEZ."""
    info = {"model": None, "messages": 0, "system_bytes": 0, "tools": 0,
            "body_bytes": len(body) if body else 0, "stream": False}
    if not body:
        return info, None
    try:
        p = json.loads(body.decode("utf-8"))
    except Exception:
        return info, None
    info["model"] = p.get("model")
    info["stream"] = bool(p.get("stream"))
    msgs = p.get("messages") or []
    info["messages"] = len(msgs)
    info["system_bytes"] = len(json.dumps(p.get("system", ""), ensure_ascii=False))
    info["tools"] = len(p.get("tools") or [])
    return info, p


def estimate_tokens(parsed):
    """Token sayisini yaklasik hesaplar (count_tokens desteklemeyen upstreamler icin)."""
    if not parsed or not isinstance(parsed, dict):
        return 1
    total_chars = 0
    sys_val = parsed.get("system")
    if isinstance(sys_val, str):
        total_chars += len(sys_val)
    elif isinstance(sys_val, list):
        for item in sys_val:
            if isinstance(item, dict):
                total_chars += len(item.get("text", ""))
    for m in parsed.get("messages") or []:
        c = m.get("content")
        if isinstance(c, str):
            total_chars += len(c)
        elif isinstance(c, list):
            for b in c:
                if isinstance(b, dict):
                    if b.get("type") == "text":
                        total_chars += len(b.get("text", ""))
                    elif b.get("type") == "tool_result":
                        content = b.get("content", "")
                        if isinstance(content, str):
                            total_chars += len(content)
                        elif isinstance(content, list):
                            for sub in content:
                                if isinstance(sub, dict) and "text" in sub:
                                    total_chars += len(sub.get("text", ""))
                    elif b.get("type") == "tool_use":
                        total_chars += len(json.dumps(b.get("input", {})))
    for t in parsed.get("tools") or []:
        total_chars += len(json.dumps(t))
    return max(1, int(total_chars / 3.8))



class UsageScanner:
    """SSE akisindan hem usage alanlarini hem de modelin urettigi yanit icerigini
    (metin, tool_use bloklari, thinking, hata) ayiklar; akisi geciktirmez."""

    def __init__(self):
        self.buf = ""
        self.usage = {}
        self.blocks = {}          # index -> content_block dict
        self.tool_inputs = {}      # index -> str (biriken json)
        self.openai_text = []
        self.openai_tool_calls = {}
        self.stop_reason = None
        self.stream_errors = []

    def feed(self, chunk_text):
        self.buf += chunk_text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                o = json.loads(payload)
            except Exception:
                continue

            # Usage yakalama
            u = (o.get("message") or {}).get("usage") or o.get("usage")
            if isinstance(u, dict):
                for k, v in u.items():
                    if isinstance(v, int):
                        # message_delta output_tokens kumulatiftir -> son deger kazanir
                        self.usage[k] = v

            ev_type = o.get("type")

            # Anthropic SSE
            if ev_type == "content_block_start":
                idx = o.get("index", 0)
                cb = o.get("content_block") or {}
                self.blocks[idx] = dict(cb)
                if cb.get("type") == "tool_use":
                    self.tool_inputs[idx] = ""
            elif ev_type == "content_block_delta":
                idx = o.get("index", 0)
                delta = o.get("delta") or {}
                dtype = delta.get("type")
                if dtype == "text_delta":
                    txt = delta.get("text", "")
                    if idx not in self.blocks:
                        self.blocks[idx] = {"type": "text", "text": ""}
                    self.blocks[idx]["text"] = self.blocks[idx].get("text", "") + txt
                elif dtype == "input_json_delta":
                    pj = delta.get("partial_json", "")
                    self.tool_inputs[idx] = self.tool_inputs.get(idx, "") + pj
                elif dtype == "thinking_delta":
                    th = delta.get("thinking", "")
                    if idx not in self.blocks:
                        self.blocks[idx] = {"type": "thinking", "thinking": ""}
                    self.blocks[idx]["thinking"] = self.blocks[idx].get("thinking", "") + th
            elif ev_type == "content_block_stop":
                idx = o.get("index", 0)
                if idx in self.tool_inputs and idx in self.blocks:
                    raw_in = self.tool_inputs[idx]
                    try:
                        self.blocks[idx]["input"] = json.loads(raw_in) if raw_in else {}
                    except Exception:
                        self.blocks[idx]["input"] = raw_in
            elif ev_type == "message_delta":
                delta = o.get("delta") or {}
                if "stop_reason" in delta:
                    self.stop_reason = delta.get("stop_reason")
            elif ev_type == "error":
                self.stream_errors.append(o.get("error") or o)

            # OpenAI SSE fallback
            choices = o.get("choices")
            if isinstance(choices, list) and choices:
                c0 = choices[0]
                delta = c0.get("delta") or {}
                c_txt = delta.get("content")
                if c_txt:
                    self.openai_text.append(c_txt)
                tc = delta.get("tool_calls")
                if isinstance(tc, list):
                    for call in tc:
                        c_idx = call.get("index", 0)
                        if c_idx not in self.openai_tool_calls:
                            self.openai_tool_calls[c_idx] = {
                                "id": call.get("id", ""),
                                "name": (call.get("function") or {}).get("name", ""),
                                "args": ""
                            }
                        f = call.get("function") or {}
                        if "name" in f and f["name"]:
                            self.openai_tool_calls[c_idx]["name"] = f["name"]
                        if "arguments" in f:
                            self.openai_tool_calls[c_idx]["args"] += f["arguments"]

    def get_content(self):
        """Toplanan bloklari standart content listesi olarak doner."""
        if self.stream_errors:
            return [{"type": "error", "error": err} for err in self.stream_errors]
        if self.blocks:
            for idx, raw_in in self.tool_inputs.items():
                if idx in self.blocks and "input" not in self.blocks[idx]:
                    try:
                        self.blocks[idx]["input"] = json.loads(raw_in) if raw_in else {}
                    except Exception:
                        self.blocks[idx]["input"] = raw_in
            return [self.blocks[k] for k in sorted(self.blocks.keys())]
        if self.openai_tool_calls:
            calls = []
            for k in sorted(self.openai_tool_calls.keys()):
                item = self.openai_tool_calls[k]
                try:
                    inp = json.loads(item["args"])
                except Exception:
                    inp = item["args"]
                calls.append({"type": "tool_use", "id": item["id"], "name": item["name"], "input": inp})
            if self.openai_text:
                return [{"type": "text", "text": "".join(self.openai_text)}] + calls
            return calls
        if self.openai_text:
            return [{"type": "text", "text": "".join(self.openai_text)}]
        return []


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _serve(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Pano yalnizca yerel; upstream'e hic gitmez.
        if self.path.startswith("/__bayqus"):
            if self.path.startswith("/__bayqus/data"):
                cfg = router.get_config()
                try:
                    payload = stats.build()
                except Exception as e:
                    payload = {"hata": f"{type(e).__name__}: {e}", "istek": 0}
                try:
                    def_r_name = (cfg.get("default") or {}).get("name", "gateway")
                    payload["claude_groups"] = sessions.get_claude_desktop_groups_data(default_route=def_r_name)
                    payload["group_pins"] = sessions.group_pins()
                    payload["subagent_pins"] = sessions.subagent_pins()
                    payload["group_subagent_pins"] = sessions.group_subagent_pins()
                    # MCP Sunucu Durumlari
                    try:
                        groups_mcp = {}
                        for g in payload.get("claude_groups", []):
                            gname = g["name"]
                            groups_mcp[gname] = mcp_manager.get_group_mcp_status(gname)
                        payload["groups_mcp"] = groups_mcp
                        payload["all_mcp_servers"] = mcp_manager.discover_all_servers()
                    except Exception as e_mcp:
                        payload["groups_mcp"] = {}
                        payload["all_mcp_servers"] = {}
                        print(f"[pano] mcp verisi alinirken hata: {e_mcp}")
                    payload["oturumlar"] = sessions.snapshot()
                    payload["proje_kurallari"] = sessions.project_pins()
                    payload["tum_projeler"] = sessions.list_all_projects()
                    payload["default_route"] = def_r_name
                    payload["routes_config"] = cfg
                    payload["runtime_config"] = {
                        "mode": MODE,
                        "mock_classifier": mocks.is_enabled(),
                        "port": PORT,
                        "upstream_force": FORCE_UPSTREAM,
                    }
                    payload["rotalar"] = [
                        {"ad": r_["name"], "upstream": r_["upstream"],
                         "enabled": r_.get("enabled", True),
                         "model_rewrite": r_.get("model_rewrite")}
                        for r_ in router.enabled_routes(cfg)
                                  + [cfg["default"]]]

                    # Akilli Ozetleyici & Prefix Cache Bilgisi
                    try:
                        raw_key = db.get_setting("ai_studio_api_key", "")
                        masked_key = (raw_key[:6] + "..." + raw_key[-4:]) if len(raw_key) > 12 else ("*" * len(raw_key))
                        sum_settings = db.get_all_settings()
                        sum_settings["has_api_key"] = bool(raw_key)
                        sum_settings["masked_api_key"] = masked_key
                        payload["summarizer_settings"] = sum_settings
                        payload["cache_stats"] = db.get_cache_stats()
                        payload["bridge_files"] = agent_bridge.count_bridge_files()
                        payload["pending_summaries"] = agent_bridge.list_pending()
                    except Exception as e_sum:
                        payload["summarizer_settings"] = {}
                        payload["cache_stats"] = {}
                        payload["bridge_files"] = {}
                        payload["pending_summaries"] = []
                        print(f"[pano] ozetleyici verisi alinirken hata: {e_sum}")
                except Exception as e:
                    payload["oturumlar"] = []
                    payload["rotalar"] = []
                    payload["oturum_hatasi"] = f"{type(e).__name__}: {e}"
                self._serve(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                            "application/json; charset=utf-8")
            elif self.path.startswith("/__bayqus/history"):
                parsed_url = urllib.parse.urlparse(self.path)
                qs = urllib.parse.parse_qs(parsed_url.query)
                req_id = qs.get("id", [None])[0]
                if req_id:
                    try:
                        detail = db.get_request_detail(int(req_id))
                        if detail:
                            self._serve(json.dumps(detail, ensure_ascii=False).encode("utf-8"),
                                        "application/json; charset=utf-8")
                        else:
                            self._fail(404, "kayit bulunamadi")
                    except Exception as e_det:
                        self._fail(400, f"gecersiz id: {e_det}")
                    return
                limit = int(qs.get("limit", ["50"])[0])
                offset = int(qs.get("offset", ["0"])[0])
                session_id = qs.get("session", [None])[0]
                search = qs.get("q", [None])[0]
                hist = db.get_history(limit=limit, offset=offset, session_id=session_id, search=search)
                self._serve(json.dumps(hist, ensure_ascii=False).encode("utf-8"),
                            "application/json; charset=utf-8")
                return
            else:
                self._serve(dashboard.PAGE.encode("utf-8"),
                            "text/html; charset=utf-8")
            return
        self._proxy("GET")

    def do_POST(self):
        if self.path.startswith("/__bayqus"):
            self._control()
            return
        self._proxy("POST")

    def _control(self):
        """Yerel pano komutlari. Upstream'e gitmez."""
        try:
            ln = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            ln = 0
        raw = self.rfile.read(min(ln, 1 << 20)) if ln > 0 else b""

        origin = (self.headers.get("Origin") or "").lower()
        ctype = (self.headers.get("Content-Type") or "").lower()
        if origin and "127.0.0.1" not in origin and "localhost" not in origin:
            self._fail(403, "yabanci koken")
            return
        if "application/json" not in ctype:
            self._fail(415, "json bekleniyor")
            return
        try:
            req = json.loads(raw or b"{}")
        except Exception as e:
            self._fail(400, f"bozuk govde: {e}")
            return

        cfg = router.get_config()

        # Proje sabitleme
        if self.path.startswith("/__bayqus/proje"):
            proje = str(req.get("project") or "")
            rota = req.get("route") or ""
            if rota and rota not in router.by_name(cfg):
                self._serve(json.dumps(
                    {"ok": False, "mesaj": f"bilinmeyen rota: {rota}"}
                ).encode("utf-8"), "application/json; charset=utf-8")
                return
            ok, mesaj = sessions.pin_project(proje, rota)
            print(f"[pano] proje kurali: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Oturum sabitleme
        if self.path.startswith("/__bayqus/pin"):
            sid = str(req.get("session") or "")
            rota = req.get("route") or ""
            if rota and rota not in router.by_name(cfg):
                self._serve(json.dumps(
                    {"ok": False, "mesaj": f"bilinmeyen rota: {rota}"}
                ).encode("utf-8"), "application/json; charset=utf-8")
                return
            ok, mesaj = sessions.pin(sid, rota)
            print(f"[pano] sabitleme: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Grup sabitleme
        if self.path.startswith("/__bayqus/group-pin"):
            gname = str(req.get("group") or "")
            rota = req.get("route") or ""
            if rota and rota not in router.by_name(cfg):
                self._serve(json.dumps({"ok": False, "mesaj": f"bilinmeyen rota: {rota}"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            ok, mesaj = sessions.pin_group(gname, rota)
            print(f"[pano] grup kurali: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Grup alt-ajan sabitleme
        if self.path.startswith("/__bayqus/group-subagent-pin"):
            gname = str(req.get("group") or "")
            rota = req.get("route") or ""
            if rota and rota not in router.by_name(cfg):
                self._serve(json.dumps({"ok": False, "mesaj": f"bilinmeyen rota: {rota}"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            ok, mesaj = sessions.pin_group_subagent(gname, rota)
            print(f"[pano] grup alt-ajan kurali: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Sohbet alt-ajan sabitleme
        if self.path.startswith("/__bayqus/subagent-pin"):
            sid = str(req.get("session") or "")
            rota = req.get("route") or ""
            if rota and rota not in router.by_name(cfg):
                self._serve(json.dumps({"ok": False, "mesaj": f"bilinmeyen rota: {rota}"}).encode("utf-8"), "application/json; charset=utf-8")
                return
            ok, mesaj = sessions.pin_subagent(sid, rota)
            print(f"[pano] sohbet alt-ajan kurali: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # MCP Sunucu Acma / Kapatma (Toggle)
        if self.path.startswith("/__bayqus/mcp-toggle"):
            gname = str(req.get("group") or "")
            sname = str(req.get("server") or "")
            disabled = bool(req.get("disabled", False))
            ok, mesaj = mcp_manager.set_server_disabled(gname, sname, disabled)
            print(f"[pano] mcp toggle: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # MCP Hizli Mod (Preset)
        if self.path.startswith("/__bayqus/mcp-preset"):
            gname = str(req.get("group") or "")
            preset = str(req.get("preset") or "")
            ok, mesaj = mcp_manager.apply_preset(gname, preset)
            print(f"[pano] mcp preset: {mesaj}")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Rota acma/kapatma (Toggle)
        if self.path.startswith("/__bayqus/routes/toggle"):
            name = str(req.get("name") or "")
            enabled = bool(req.get("enabled"))
            ok, mesaj = router.toggle_route(name, enabled)
            print(f"[pano] rota toggle: {name} -> {enabled} ({mesaj})")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Rota kaydetme (Ekleme / Guncelleme)
        if self.path.startswith("/__bayqus/routes/save"):
            route_data = req.get("route") or {}
            ok, mesaj = router.save_route(route_data)
            print(f"[pano] rota kaydet: {route_data.get('name')} ({mesaj})")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Rota silme
        if self.path.startswith("/__bayqus/routes/delete"):
            name = str(req.get("name") or "")
            ok, mesaj = router.delete_route(name)
            print(f"[pano] rota sil: {name} ({mesaj})")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Tum yapilandirmayi kaydetme (JSON Editor veya formdan)
        if self.path.startswith("/__bayqus/routes/all"):
            cfg_data = req.get("config") or {}
            ok, mesaj = router.save_config(cfg_data)
            print(f"[pano] tum rotalar kaydedildi ({mesaj})")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj},
                                   ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Varsayilan (default) rotayi degistirme
        if self.path.startswith("/__bayqus/default-route"):
            route_name = str(req.get("route") or "")
            ok, mesaj = router.set_default_route(route_name)
            print(f"[pano] varsayilan rota degisti: {route_name} ({mesaj})")
            self._serve(json.dumps({"ok": ok, "mesaj": mesaj}, ensure_ascii=False).encode("utf-8"),
                        "application/json; charset=utf-8")
            return

        # Proxy calisma ayarlari (Mod, mock classifier)
        if self.path.startswith("/__bayqus/config"):
            global MODE
            if "mode" in req and req["mode"] in ("prune", "shadow", "passthrough"):
                MODE = req["mode"]
            if "mock_classifier" in req:
                mocks.set_enabled(bool(req["mock_classifier"]))
            print(f"[pano] ayar guncellendi: mode={MODE}, mock={mocks.is_enabled()}")
            self._serve(json.dumps({
                "ok": True,
                "mesaj": f"Mod: {MODE}, Taklit: {mocks.is_enabled()}",
                "runtime_config": {
                    "mode": MODE,
                    "mock_classifier": mocks.is_enabled()
                }
            }, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Ozetleyici ayarlari kaydetme
        if self.path.startswith("/__bayqus/summarizer/settings"):
            if "summarizer_mode" in req:
                db.set_setting("summarizer_mode", req["summarizer_mode"])
            if "enable_ai_summarizer" in req:
                db.set_setting("enable_ai_summarizer", "true" if req["enable_ai_summarizer"] else "false")
            if "preferred_gemini_model" in req:
                db.set_setting("preferred_gemini_model", req["preferred_gemini_model"])
            if "block_size" in req:
                db.set_setting("block_size", str(int(req["block_size"])))
            if "keep_recent_messages" in req:
                db.set_setting("keep_recent_messages", str(int(req["keep_recent_messages"])))
            if "ai_studio_api_key" in req and req["ai_studio_api_key"].strip():
                db.set_setting("ai_studio_api_key", req["ai_studio_api_key"].strip())
            print(f"[pano] ozetleyici ayarlari guncellendi")
            self._serve(json.dumps({"ok": True, "mesaj": "Özetleyici ayarları kaydedildi!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Ozetleyici onbellegi temizleme
        if self.path.startswith("/__bayqus/summarizer/clear-cache"):
            db.clear_cache()
            print(f"[pano] prefix onbellegi temizlendi")
            self._serve(json.dumps({"ok": True, "mesaj": "Prefix önbelleği temizlendi!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # İstek geçmişi temizleme
        if self.path.startswith("/__bayqus/history/clear"):
            db.clear_history()
            print(f"[pano] istek gecmisi temizlendi")
            self._serve(json.dumps({"ok": True, "mesaj": "İstek geçmişi temizlendi!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Gemini API testi
        if self.path.startswith("/__bayqus/summarizer/test-gemini"):
            api_key = req.get("api_key", "").strip() or db.get_setting("ai_studio_api_key", "")
            model = req.get("model", "").strip() or db.get_setting("preferred_gemini_model", "gemini-3.1-flash-lite")
            if not api_key:
                self._serve(json.dumps({"ok": False, "mesaj": "API anahtarı bulunamadı!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                return
            s, status = agent_bridge.call_gemini_summary("Test: Merhaba, bu bir sistem denemesidir.", api_key, model)
            if s:
                self._serve(json.dumps({"ok": True, "mesaj": f"Bağlantı Başarılı! ({status})", "sample": s[:120]}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            else:
                self._serve(json.dumps({"ok": False, "mesaj": f"Bağlantı Hatası: {status}"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        # Ajan ozeti teslim etme (Antigravity veya harici)
        if self.path.startswith("/__bayqus/summarizer/submit-summary"):
            prefix_hash = req.get("prefix_hash", "").strip()
            summary_text = req.get("summary_text", "").strip()
            agent_name = req.get("agent_name", "antigravity_agent").strip()
            if prefix_hash and summary_text:
                agent_bridge.save_agent_summary(prefix_hash, summary_text, agent_name)
                self._serve(json.dumps({"ok": True, "mesaj": "Ajan özeti kaydedildi!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            else:
                self._serve(json.dumps({"ok": False, "mesaj": "Eksik parametre!"}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return

        self._fail(404, "bilinmeyen komut")

    def _fail(self, code, mesaj):
        """JSON hata; govde okunmus olmali."""
        body = json.dumps({"ok": False, "mesaj": mesaj},
                          ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_DELETE(self):
        self._proxy("DELETE")

    def _maybe_prune(self, method, parsed, route, session_id=""):
        """Budama planini uygular. (yeni_govde_veya_None, plan) doner."""
        if not route.get("prune", True):
            return None, None
        if MODE == "passthrough" or not parsed or method != "POST":
            return None, None
        if not self.path.startswith("/v1/messages"):
            return None, None
        if "count_tokens" in self.path:
            return None, None
        try:
            plan = pruner.plan(parsed, session_id)
        except Exception as e:
            print(f"           !!! budama atlandi ({type(e).__name__}: {e})")
            return None, None
        if not plan.get("applied"):
            return None, plan
        return (plan["body"] if MODE == "prune" else None), plan

    def _print_plan(self, plan, before, after):
        if not plan:
            return
        if not plan.get("applied"):
            print(f"           budama: yok — {plan.get('reason')}")
            return
        s = plan.get("stats") or {}
        pct = (1 - after / before) * 100 if before else 0.0
        etiket = "budandi" if MODE == "prune" else "GOLGE (gonderilmedi)"
        sicak = "hayir" if plan.get("cold") else "evet"
        onek_durum = "=" if plan.get("prefix_stable") else "YENI"
        saved_tok = plan.get("tokens_saved") if plan.get("tokens_saved") is not None else max(0, (before - after) // 4)
        arc = plan.get("archive_cut", plan.get("cutoff"))
        hot = plan.get("hot_cut", plan.get("cutoff"))
        total = plan.get("total_messages")
        print(f"           budama[{etiket}]: arsiv=0..{arc}  soguk={arc}..{hot}  "
              f"sicak={hot}..{total}  sicak={sicak}  "
              f"onek={plan.get('prefix_hash')} {onek_durum}  yontem={plan.get('summary_method', 'det')}")
        print(f"           govde {n(before)}B -> {n(after)}B  "
              f"({pct:.1f}% kucuk, ~{n(saved_tok)} token)")

    def _proxy(self, method):
        t0 = time.time()
        body = None
        if "Content-Length" in self.headers:
            body = self.rfile.read(int(self.headers["Content-Length"]))

        req_info, parsed = analyze_request(body)
        # Claude Code her istege bunu koyar ve sohbet boyunca sabittir;
        # model degisse bile degismez. Oturum bazli yonlendirmenin dayanagi.
        sid = self.headers.get("x-claude-code-session-id") or ""
        agent_id = self.headers.get("x-claude-code-agent-id") or ""
        req_info["session"] = sid
        req_info["agent"] = agent_id
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] --> {method} {self.path}")
        print(f"           model={req_info['model']}  "
              f"mesaj={req_info['messages']}  arac={req_info['tools']}  "
              f"govde={n(req_info['body_bytes'])}B  stream={req_info['stream']}")
        if sid or agent_id:
            proje = sessions.project_for(sid, agent_id=agent_id)
            print(f"           oturum={(sid or agent_id)[:8]}"
                  + (f" [{proje}]" if proje else "")
                  + (f"  altajan={agent_id[:8]}" if agent_id else ""))

        # Yerel count_tokens cevabi (upstream 404 ve gereksiz ag gecikmesini onler)
        if method == "POST" and self.path.startswith("/v1/messages/count_tokens"):
            tok_count = count_tokens_locally(body)
            resp_bytes = json.dumps({"input_tokens": tok_count}).encode("utf-8")
            self._serve(resp_bytes, "application/json; charset=utf-8")
            ms = int((time.time() - t0) * 1000)
            print(f"           ⚡ YEREL TOKEN SAYIMI (tiktoken): {tok_count:,} token ({ms} ms)")
            return

        agent_id = req_info.get("agent") or ""
        pin, pin_kaynak = sessions.pinned(sid, agent_id=agent_id)
        cfg = router.get_config()
        route, pinned_used, pin_uyari = router.pick(cfg, req_info["model"], pin)
        if pin_uyari:
            print(f"           !!! {pin_uyari}")
        upstream = FORCE_UPSTREAM or route["upstream"]
        sessions.note(sid, req_info["model"], route["name"], agent_id=agent_id)

        # Proje / Grup bazli MCP arac budama (kullanilmamis devre disi sunucu toollari)
        if parsed and "tools" in parsed and parsed["tools"]:
            dis_servers = mcp_manager.get_disabled_servers_for_session(sid, agent_id=agent_id)
            if dis_servers:
                parsed, t_stats = pruner.prune_tools(parsed, dis_servers)
                if t_stats.get("pruned_tools", 0) > 0:
                    body = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
                    req_info["tools"] = t_stats["kept_tools"]
                    req_info["pruned_tools"] = t_stats["pruned_tools"]
                    print(f"           arac budandi: {t_stats['pruned_tools']}/{t_stats['total_tools']} MCP araci elendi (-{n(t_stats['saved_bytes'])}B)")

        # Model adini rotanin istedigi ada cevir. Budamadan ONCE yapilmali:
        # pruner govdeyi `parsed`'dan yeniden kurar, yeni ad oraya gitsin.
        rw = router.rewrite_model(route, parsed)
        if rw:
            body = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
            print(f"           model yeniden yazildi: {rw[0]} -> {rw[1]}")
            req_info["model_sent"] = rw[1]

        orig_bytes = len(body) if body else 0
        new_body, plan = self._maybe_prune(method, parsed, route, sid)
        planned_bytes = len(plan["body"]) if (plan and plan.get("applied")) else orig_bytes
        if new_body is not None:
            body = new_body
        elif parsed and "anthropic.com" not in upstream:
            pruner.normalize_cache_controls(parsed)
            body = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
        sent_bytes = len(body) if body else 0
        req_info["route"] = route["name"]
        req_info["upstream"] = upstream
        req_info["method"] = method
        req_info["path"] = self.path
        self._print_plan(plan, orig_bytes, planned_bytes)

        sent_parsed = None
        if body:
            try:
                sent_parsed = json.loads(body.decode("utf-8"))
            except Exception:
                sent_parsed = parsed
        else:
            sent_parsed = parsed

        incoming = {k: v for k, v in self.headers.items()
                    if k.lower() not in HOP_BY_HOP}
        try:
            headers, cred = router.build_headers(incoming, route)
        except router.RouteError as e:
            print(f"[{ts}] !!! ROTA REDDEDILDI: {e}")
            self.send_error(502, "route rejected")
            return

        # Gateway uyumlulugu: Anthropic disindaki gateway'ler (LiteLLM, OneAPI, Ollama vb.)
        # sadece standart Anthropic beta basliklarini tanir. Yeni eklenen deneysel
        # veya taninmayan basliklar upstream KV onbellegini devre disi birakir.
        if "anthropic.com" not in upstream:
            allowed_betas = {
                "claude-code-20250219",
                "interleaved-thinking-2025-05-14",
                "mid-conversation-system-2026-04-07",
                "tool-search-tool-2025-10-19",
                "effort-2025-11-24",
                "fallback-credit-2026-06-01"
            }
            for bk in ("anthropic-beta", "Anthropic-Beta"):
                if bk in headers and headers[bk]:
                    betas = [b.strip() for b in headers[bk].split(",")]
                    safe_betas = [b for b in betas if b in allowed_betas]
                    headers[bk] = ",".join(safe_betas) if safe_betas else "claude-code-20250219"

            for hk in list(headers.keys()):
                hl = hk.lower()
                if hl.startswith("anthropic-client-") or hl == "x-client-request-id":
                    del headers[hk]

            if body and self.path.startswith("/v1/messages"):
                try:
                    p_obj = json.loads(body.decode("utf-8"))
                    body_modified = False
                    for sk in ("context_management", "diagnostics"):
                        if sk in p_obj:
                            del p_obj[sk]
                            body_modified = True
                    if body_modified:
                        body = json.dumps(p_obj, ensure_ascii=False).encode("utf-8")
                except Exception:
                    pass

        if body:
            headers["Content-Length"] = str(len(body))

        try:
            print(f"           rota={route['name']}"
                  + (f"  ({pin_kaynak.upper()} KURALI)" if pinned_used else "")
                  + f" -> {upstream}  kimlik={cred}")
            if body and self.path.startswith("/v1/messages") and "count_tokens" not in self.path and len(body) > 50000:
                try:
                    with open(os.path.join(LOG_DIR, "debug_last_sent.json"), "wb") as df:
                        df.write(body)
                    with open(os.path.join(LOG_DIR, "debug_last_headers.json"), "w", encoding="utf-8") as hf:
                        json.dump(headers, hf, indent=2)
                except Exception:
                    pass
            req = urllib.request.Request(upstream + self.path, data=body,
                                         headers=headers, method=method)
            with urllib.request.urlopen(req, context=SSL_CTX, timeout=600) as r:
                ctype = r.headers.get("Content-Type", "")
                streaming = "text/event-stream" in ctype.lower()

                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() not in HOP_BY_HOP:
                        self.send_header(k, v)

                if streaming:
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    scanner = UsageScanner()
                    total = 0
                    while True:
                        chunk = r.read(4096)
                        if not chunk:
                            break
                        total += len(chunk)
                        # once istemciye akit (gecikme eklemeyelim)
                        self.wfile.write(b"%X\r\n" % len(chunk))
                        self.wfile.write(chunk)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                        scanner.feed(chunk.decode("utf-8", "replace"))
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    usage = scanner.usage
                    resp_bytes = total
                    resp_content = scanner.get_content()
                else:
                    data = r.read()
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    resp_bytes = len(data)
                    usage = {}
                    resp_content = None
                    try:
                        o = json.loads(data)
                        usage = (o.get("message") or {}).get("usage") or o.get("usage") or {}
                        resp_content = (o.get("message") or {}).get("content") or o.get("content")
                    except Exception:
                        resp_content = [{"type": "raw", "data": data[:2000].decode("utf-8", "replace")}]

                ms = int((time.time() - t0) * 1000)
                self._report(r.status, ms, req_info, usage, resp_bytes,
                             plan, orig_bytes, planned_bytes, sent_bytes,
                             sent_parsed=sent_parsed, resp_content=resp_content)

        except urllib.error.HTTPError as e:
            if e.code == 404 and "count_tokens" in self.path:
                token_count = estimate_tokens(parsed)
                resp_data = json.dumps({"input_tokens": token_count}).encode("utf-8")
                ms = int((time.time() - t0) * 1000)
                print(f"[{ts}] <-- 200 ({ms}ms)  yerel count_tokens fallback: {token_count} token (upstream 404 onlendi)")
                self._report(200, ms, req_info, {"input_tokens": token_count}, len(resp_data),
                             plan, orig_bytes, planned_bytes, sent_bytes, phase="fallback:count_tokens",
                             sent_parsed=sent_parsed, resp_content={"input_tokens": token_count})
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)
                return

            data = e.read()
            ms = int((time.time() - t0) * 1000)
            err_msg = f"HTTP {e.code}: {data[:300].decode('utf-8', 'replace')}"
            print(f"[{ts}] <-- {err_msg}")
            if MODE == "prune" and plan and plan.get("applied"):
                print("           ^ budama ACIKTI — hata budamadan olabilir. "
                      "BAYQUS_MODE=shadow ile dogrulayin.")
            err_content = [{"type": "error", "code": e.code, "message": err_msg}]
            self._report(e.code, ms, req_info, {}, len(data),
                         plan, orig_bytes, planned_bytes, sent_bytes, error=err_msg,
                         sent_parsed=sent_parsed, resp_content=err_content)
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            ms = int((time.time() - t0) * 1000)
            err_msg = f"{type(e).__name__}: {e}"
            print(f"[{ts}] !!! {err_msg}")
            err_content = [{"type": "exception", "error": err_msg}]
            self._report(502, ms, req_info, {}, 0,
                         plan, orig_bytes, planned_bytes, sent_bytes, error=err_msg,
                         sent_parsed=sent_parsed, resp_content=err_content)
            try:
                self.send_error(502, str(e))
            except Exception:
                pass

    def _report(self, status, ms, req_info, usage, resp_bytes,
                plan, orig_bytes, planned_bytes, sent_bytes, phase=None, error=None,
                sent_parsed=None, resp_content=None):
        inp = usage.get("input_tokens", 0)
        cr = usage.get("cache_read_input_tokens", 0)
        cc = usage.get("cache_creation_input_tokens", 0)
        out = usage.get("output_tokens", 0)
        ctx = inp + cr + cc
        hit = (cr / ctx * 100) if ctx else 0.0

        print(f"           <-- {status} ({ms}ms)  yanit={n(resp_bytes)}B")
        if ctx or out:
            print(f"           baglam={n(ctx)}  girdi={n(inp)}  "
                  f"cache-oku={n(cr)}  cache-yaz={n(cc)}  cikti={n(out)}  "
                  f"isabet={hit:.1f}%")
        print()

        rec = {"ts": datetime.now().isoformat(), "status": status, "ms": ms,
               "mode": MODE,
               "model": req_info["model"], "messages": req_info["messages"],
               "tools": req_info["tools"],
               "req_bytes": orig_bytes, "planned_bytes": planned_bytes,
               "sent_bytes": sent_bytes,
               "resp_bytes": resp_bytes, "context": ctx, "input": inp,
               "cache_read": cr, "cache_creation": cc, "output": out,
               "hit_pct": round(hit, 2), "phase": phase or MODE,
               "route": req_info.get("route"), "upstream": req_info.get("upstream"),
               "model_sent": req_info.get("model_sent"),
               "session": req_info.get("session"), "agent": req_info.get("agent"),
               "error": error}
        if plan:
            rec["prune"] = {
                "applied": plan.get("applied"),
                "reason": plan.get("reason"),
                "session": plan.get("session"),
                "cold": plan.get("cold"),
                "cutoff": plan.get("cutoff"),
                "total_messages": plan.get("total_messages"),
                "prefix_hash": plan.get("prefix_hash"),
                "prefix_stable": plan.get("prefix_stable"),
                "stats": plan.get("stats"),
            }
        with open(METRICS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # Son 5000 istek icerigi kaydi (SQLite halka tamponu)
        try:
            sys_val = sent_parsed.get("system") if isinstance(sent_parsed, dict) else None
            msgs_val = sent_parsed.get("messages") if isinstance(sent_parsed, dict) else None
            prune_applied = bool(plan and plan.get("applied"))
            p_info = None
            if prune_applied:
                p_info = {
                    "cutoff": plan.get("cutoff"),
                    "total_messages": plan.get("total_messages"),
                    "stats": plan.get("stats"),
                    "reason": plan.get("reason"),
                }
            db.record_request(
                session_id=req_info.get("session") or "",
                agent_id=req_info.get("agent") or "",
                method=req_info.get("method") or "POST",
                path=req_info.get("path") or self.path,
                status_code=status,
                duration_ms=ms,
                model=req_info.get("model"),
                model_sent=req_info.get("model_sent") or req_info.get("model"),
                route=req_info.get("route"),
                upstream=req_info.get("upstream"),
                system_prompt=sys_val,
                messages=msgs_val,
                response_content=resp_content,
                usage=usage,
                prune_applied=prune_applied,
                prune_info=p_info
            )
        except Exception as e_rec:
            print(f"[!] İstek geçmişi kaydedilirken hata: {e_rec}")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # keep-alive kapanmalari normaldir; traceback basmayalim
        et = sys.exc_info()[0]
        if et in (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            return
        super().handle_error(request, client_address)


def auto_wrap_claude_code():
    """Claude Desktop veya Claude Code guncellendiginde yeni olusan versiyonlari otomatik sarar."""
    base = os.path.expandvars(r"%APPDATA%\Claude\claude-code")
    wrapper_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wrapper", "wrapper.exe")
    if not os.path.exists(wrapper_bin) or not os.path.isdir(base):
        return
    try:
        for item in os.listdir(base):
            vdir = os.path.join(base, item)
            if not os.path.isdir(vdir):
                continue
            c_exe = os.path.join(vdir, "claude.exe")
            c_real = os.path.join(vdir, "claude_real.exe")
            if os.path.exists(c_exe) and not os.path.exists(c_real):
                try:
                    if os.path.getsize(c_exe) > 50 * 1024 * 1024:
                        os.rename(c_exe, c_real)
                        shutil.copy2(wrapper_bin, c_exe)
                        print(f"[auto-wrap] {item}/claude.exe sarildi (wrapper kuruldu)")
                except Exception as e:
                    pass
    except Exception:
        pass


def _wrap_watcher_loop():
    while True:
        try:
            auto_wrap_claude_code()
        except Exception:
            pass
        time.sleep(10)


if __name__ == "__main__":
    auto_wrap_claude_code()
    threading.Thread(target=_wrap_watcher_loop, daemon=True).start()
    if MODE not in ("prune", "shadow", "passthrough"):
        sys.exit(f"gecersiz BAYQUS_MODE={MODE}")
    pins, proj_pins = sessions.load()
    problems = router.validate(ROUTES)
    if problems:
        print("!!! ROTA YAPILANDIRMASI REDDEDILDI:")
        for p_ in problems:
            print(f"    {p_}")
        sys.exit(1)
    print(f"bayqus-proxy  :{PORT}")
    if FORCE_UPSTREAM:
        print(f"upstream ZORLANDI: {FORCE_UPSTREAM} (yonlendirme devre disi)")
    for r_ in router.enabled_routes(ROUTES) + [ROUTES["default"]]:
        pats = ",".join(r_.get("model_contains") or ["*"])
        rw_ = r_.get("model_rewrite")
        print(f"  {pats:<24} -> {r_['upstream']}  "
              f"budama={'acik' if r_.get('prune', True) else 'kapali'}"
              + (f"  model={rw_}" if rw_ else ""))
    if pins:
        print(f"oturum sabitlemesi: {len(pins)} adet")
        for sid_, rota_ in pins.items():
            print(f"  {sid_[:8]} -> {rota_}")
    if proj_pins:
        print(f"proje kurali: {len(proj_pins)} adet")
        for yol_, rota_ in proj_pins.items():
            print(f"  {yol_} -> {rota_}")
    print(f"mod: {MODE}   blok={pruner.BLOCK} koru={pruner.KEEP_RECENT} "
          f"soguk-tampon={pruner.COLD_BUFFER} ttl={pruner.TTL}s "
          f"min-mesaj={pruner.MIN_MESSAGES}")
    print(f"metrik: {METRICS}\n")
    Server(("127.0.0.1", PORT), Handler).serve_forever()
