#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, subprocess, shlex, html
from pathlib import Path
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

REPOS = [
    {"name": "jurist",   "unit": "jurist.service",             "path": "/root/projects/jurist"},
    {"name": "persobi",  "unit": "persobi.service",            "path": "/root/projects/persobi-content"},
    {"name": "deniska",  "unit": "deniska-dashboard.service",  "path": "/root/projects/deniska-dashboard"},
    {"name": "testbot",  "unit": "testbot.service",            "path": "/root/projects/testbot"},
]

PASSPORT_FILE = "/root/docs/DENISKA_PASSPORT.md"

def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store"
    return resp

def run(cmd: str, timeout: float = 5.0) -> subprocess.CompletedProcess:
    return subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=timeout)

def read_state_files():
    rows = []
    for r in REPOS:
        state_path = Path(r["path"]) / "docs" / "STATE.json"
        item = {"name": r["name"], "unit": r["unit"], "path": r["path"],
                "status": "unknown", "branch": "-", "origin": "-", "dirty": "-"}
        try:
            if state_path.exists():
                data = json.loads(state_path.read_text(encoding="utf-8"))
                item.update({k: data.get(k, item.get(k)) for k in ["status","branch","origin","dirty"]})
        except Exception:
            pass
        rows.append(item)
    return rows

def collect_status_quick():
    """Пытаемся взять готовый JSON скриптом; если не вышло — читаем STATE.json в репо."""
    try:
        cp = run("bash /root/bin/deniska-status.sh", timeout=3.0)
        if cp.returncode == 0:
            data = json.loads(cp.stdout.strip())
            rows = data.get("rows") or []
            byname = {r["name"]: r for r in rows if isinstance(r, dict) and "name" in r}
            out = []
            for r in REPOS:
                base = {"name": r["name"], "unit": r["unit"], "path": r["path"],
                        "status": "unknown", "branch": "-", "origin": "-", "dirty": "-"}
                base.update(byname.get(r["name"], {}))
                out.append(base)
            return out
    except Exception:
        pass
    return read_state_files()

@app.route("/ping")
def ping():
    return _no_store(jsonify({"ok": True}))

@app.route("/api/services")
def api_services():
    rows = collect_status_quick()
    return _no_store(jsonify({"rows": rows}))

@app.route("/logs")
def logs():
    unit = request.args.get("unit", "deniska-dashboard.service")
    try:
        cp = run(f"journalctl -u {shlex.quote(unit)} -n 200 --no-pager", timeout=3.5)
        body = html.escape(cp.stdout[-10000:] if cp.stdout else cp.stderr)
    except Exception as e:
        body = f"error: {html.escape(str(e))}"
    html_page = f"<pre style='background:#0b0f14;color:#e5e7eb;padding:16px;white-space:pre-wrap'>{body}</pre>"
    return Response(html_page, mimetype="text/html")

@app.route("/restart")
def restart():
    unit = request.args.get("unit", "deniska-dashboard.service")
    try:
        run(f"systemctl restart {shlex.quote(unit)}", timeout=3.0)
        return _no_store(jsonify({"ok": True, "unit": unit}))
    except Exception as e:
        return _no_store(jsonify({"ok": False, "error": str(e), "unit": unit})), 500

@app.route("/docs")
def docs():
    try:
        text = Path(PASSPORT_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        text = "Паспорт не найден: " + PASSPORT_FILE
    text = html.escape(text)
    html_page = (
        "<html><head><meta charset='utf-8'/>"
        "<style>"
        ":root{--bg:#0b0f14;--txt:#e5e7eb}"
        "html,body{background:var(--bg);color:var(--txt);margin:0;"
        "font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif}"
        "pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}"
        "body{padding:20px;white-space:pre-wrap}"
        "a{color:#93c5fd}"
        "</style></head><body>" + text + "</body></html>"
    )
    return Response(html_page, mimetype="text/html")

INDEX_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Deniska Dashboard</title>
<style>
:root{
  --bg:#0b0f14;        /* общий фон */
  --panel:#111827;     /* карточки/строки */
  --text:#e5e7eb;      /* основной текст */
  --muted:#9ca3af;     /* подписи */
  --line:#232a34;      /* границы */
  --btn:#1f2937;       /* кнопка */
  --btnH:#374151;      /* hover */
  --ok:#22c55e;        /* зелёный */
  --bad:#ef4444;       /* красный */
}
html,body{
  background:var(--bg); color:var(--text);
  margin:0;
  font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
.top{
  display:flex; gap:.6rem; align-items:center;
  padding:12px 16px; background:#0f141b; position:sticky; top:0; z-index:10;
  border-bottom:1px solid var(--line);
}
.btn{
  background:var(--btn); color:var(--text);
  border:1px solid var(--line); border-radius:10px;
  padding:.55rem .9rem; cursor:pointer; text-decoration:none; display:inline-block;
}
.btn:hover{ background:var(--btnH); }
.container{ padding:14px 16px; }
.status{ font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; margin-bottom:8px; }
table{ width:100%; border-collapse:separate; border-spacing:0 10px; }
th{ color:var(--muted); font-weight:600; text-align:left; padding:10px 14px; }
td{ padding:12px 14px; background:var(--panel); border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
tr td:first-child{ border-left:1px solid var(--line); border-top-left-radius:12px; border-bottom-left-radius:12px; }
tr td:last-child{ border-right:1px solid var(--line); border-top-right-radius:12px; border-bottom-right-radius:12px; }
.mono{ font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace; }
.badge{
  display:inline-block; border-radius:999px; padding:.15rem .55rem;
  border:1px solid var(--line); background:#0f1620; color:var(--text);
}
.badge.ok{ background:rgba(34,197,94,.15); border-color:#14532d; color:#a7f3d0; }
.badge.bad{ background:rgba(239,68,68,.12); border-color:#7f1d1d; color:#fecaca; }
.pill{ padding:2px 8px; border-radius:999px; background:#0e131a; border:1px solid var(--line) }
</style>
</head>
<body>
  <div class="top">
    <button class="btn" onclick="doPing()">Ping</button>
    <button class="btn" onclick="openLogs()">Logs</button>
    <button class="btn" onclick="doRestart()">Restart</button>
    <a class="btn" href="/docs" target="_blank">📘 Docs</a>
  </div>

  <div class="container">
    <div id="status" class="status">Загрузка…</div>
    <div id="table"></div>
  </div>

<script>
async function fetchJSON(url){
  const r = await fetch(url, {cache:'no-store'});
  if(!r.ok) throw new Error('HTTP '+r.status);
  return await r.json();
}
function esc(s){return (s??'').toString().replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}

async function load(){
  try{
    document.getElementById('status').textContent='Загрузка…';
    const data = await fetchJSON('/api/services');
    const rows = data.rows||[];
    let html = '<table><thead><tr><th>Проект</th><th>Unit</th><th>Статус</th><th>Ветка</th><th>Origin</th><th>Dirty</th><th>Путь</th></tr></thead><tbody>';
    for(const r of rows){
      const ok = (r.status||'').toLowerCase()==='active';
      html += `<tr>
        <td>${esc(r.name)}</td>
        <td><span class="pill mono">${esc(r.unit)}</span></td>
        <td>${ok?'<span class="badge ok">Active</span>':'<span class="badge bad">'+esc(r.status||'?')+'</span>'}</td>
        <td>${esc(r.branch||'-')}</td>
        <td class="mono">${esc(r.origin||'-')}</td>
        <td>${esc(r.dirty||'-')}</td>
        <td class="mono">${esc(r.path||'')}</td>
      </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('table').innerHTML = html;
    document.getElementById('status').textContent='Готово';
  }catch(e){
    document.getElementById('status').textContent='Ошибка: '+e.message;
  }
}

async function doPing(){
  try{ await fetchJSON('/ping'); document.getElementById('status').textContent='Ping: ok'; }
  catch(e){ document.getElementById('status').textContent='Ping error: '+e.message; }
}
function openLogs(){ window.open('/logs','_blank'); }
async function doRestart(){
  try{ const r=await fetchJSON('/restart'); document.getElementById('status').textContent='Restart: '+(r.ok?'ok':'fail'); }
  catch(e){ document.getElementById('status').textContent='Restart error: '+e.message; }
}

load();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=18081)
