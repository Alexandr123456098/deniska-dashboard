#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, time, psutil, socket, threading, subprocess
from datetime import datetime
from flask import Flask, Response, request, jsonify, stream_with_context

PORT = int(os.getenv("DENISKA_DASH_PORT", "18081"))
HOST = "0.0.0.0"

# ЕДИНЫЙ МОЗГ
MAP_FILE = "/root/secrets/persobi_global_state.json"

SYNC_BIN = "/usr/local/bin/deniska-sync.sh"
COMPOSE_BIN = "/usr/local/bin/deniska-compose.sh"
REMOTE_ENV = "/root/secrets/deniska-remote.env"  # TG_BOT/TG_CHAT
SERVER_NAME = socket.gethostname()

app = Flask(__name__)

# --- утилиты ---------------------------------------------------------------

def load_map():
    try:
        with open(MAP_FILE, "r") as f:
            data = json.load(f)
        # ожидаем объект вида {key: {...}}; приводим к списку строк таблицы
        rows = []
        for name, repo in (data or {}).items():
            unit = (repo.get("service") if isinstance(repo, dict) else f"{name}.service")
            status = sysd_active(unit) if unit else "not-found"
            rows.append({"name": name, "repo": repo, "unit": unit, "status": status})
        return rows
    except Exception:
        return []

def load_env_vars(path):
    res = {}
    if not os.path.exists(path):
        return res
    with open(path) as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k,v=line.split("=",1)
                res[k.strip()] = v.strip().strip('"').strip("'")
    return res

TG = load_env_vars(REMOTE_ENV)

def run(cmd, timeout=None):
    return subprocess.run(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=timeout
    ).stdout

def sysd_active(unit):
    if not unit:
        return "not-found"
    code = subprocess.call(["systemctl","is-active","--quiet", unit])
    if code==0: return "active"
    if code==3: return "inactive"
    return "not-found"

def human_uptime():
    boot = datetime.fromtimestamp(psutil.boot_time())
    delta = datetime.now() - boot
    d = delta.days
    h = delta.seconds//3600
    m = (delta.seconds%3600)//60
    return f"{d}d {h}h {m}m"

# --- метрики ---------------------------------------------------------------

_metrics_ring = {"cpu":[], "ram":[]}
_RING_MAX = 60  # 60 точек ~ последняя минута

def metrics_tick():
    while True:
        try:
            cpu = psutil.cpu_percent(interval=1.0)
            ram = psutil.virtual_memory().percent
            for key,val in (("cpu",cpu),("ram",ram)):
                arr = _metrics_ring[key]
                arr.append(val)
                if len(arr) > _RING_MAX:
                    del arr[0:len(arr)-_RING_MAX]
        except Exception:
            pass

threading.Thread(target=metrics_tick, daemon=True).start()

@app.get("/metrics")
def metrics_json():
    return jsonify({
        "cpu": _metrics_ring["cpu"][-1] if _metrics_ring["cpu"] else psutil.cpu_percent(),
        "ram": _metrics_ring["ram"][-1] if _metrics_ring["ram"] else psutil.virtual_memory().percent,
        "uptime": human_uptime()
    })

@app.get("/metrics/series")
def metrics_series():
    return jsonify({
        "cpu": _metrics_ring["cpu"],
        "ram": _metrics_ring["ram"],
        "uptime": human_uptime()
    })

# --- список проектов/статусы ----------------------------------------------

def projects_table():
    return load_map()

@app.get("/api/services")
def api_services():
    return jsonify({"server": SERVER_NAME, "at": datetime.now().isoformat(), "rows": projects_table()})

@app.get("/api/ping")
def api_ping():
    out = {}
    for row in projects_table():
        out[row["name"]] = sysd_active(row["unit"])
    return jsonify({"server": SERVER_NAME, "ping": out, "at": datetime.now().isoformat()})

@app.post("/api/restart/<unit>")
def api_restart(unit):
    unit = unit.strip()
    subprocess.call(["systemctl","restart",unit])
    st = "active" if subprocess.call(["systemctl","is-active","--quiet",unit])==0 else "inactive"
    return jsonify({"ok": True, "status": st})

# --- синхронизации / compose ----------------------------------------------

def tg_notify(text):
    bot = TG.get("TG_BOT","")
    chat = TG.get("TG_CHAT","")
    if not bot or not chat:
        return
    try:
        run(f'curl -s -X POST "https://api.telegram.org/bot{bot}/sendMessage" -d "chat_id={chat}" -d "text={text}"')
    except Exception:
        pass

@app.post("/sync/<project>")
def sync_project(project):
    if not os.path.exists(SYNC_BIN):
        return jsonify({"ok":False,"msg":"sync tool not found"}), 500
    env = f". {REMOTE_ENV}; " if os.path.exists(REMOTE_ENV) else ""
    out = run(f'{env}{SYNC_BIN} 2>&1')
    return jsonify({"ok":True,"msg":out})

@app.post("/compose")
def compose():
    payload = request.get_json(force=True, silent=True) or {}
    name = (payload.get("name") or "").strip()
    sources = payload.get("sources") or []
    if not name or not sources:
        return jsonify({"ok":False,"msg":"name & sources required"}), 400
    if not os.path.exists(COMPOSE_BIN):
        return jsonify({"ok":False,"msg":"compose tool not found"}), 500
    cmd = f'{COMPOSE_BIN} {name} ' + " ".join(sources)
    out = run(cmd)
    tg_notify(f"✅ Новый бот {name} создан (сборка: {', '.join(sources)})")
    return jsonify({"ok":True,"msg":out})

# --- логи: статические и живые --------------------------------------------

@app.get("/logs/<unit>")
def logs_tail(unit):
    unit = unit.strip()
    out = run(f'journalctl -u {unit} -n 200 --no-pager 2>&1')
    return Response(f"<pre>{out}</pre>", mimetype="text/html; charset=utf-8")

@app.get("/logs/stream/<unit>")
def logs_stream(unit):
    unit = unit.strip()
    def generate():
        p = subprocess.Popen(["journalctl","-u",unit,"-f","-n","50","-o","short"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        try:
            for line in iter(p.stdout.readline, ''):
                yield f"data: {line.rstrip()}\n\n"
        finally:
            try: p.terminate()
            except Exception: pass
    headers = {"Content-Type":"text/event-stream", "Cache-Control":"no-cache", "Connection":"keep-alive"}
    return Response(stream_with_context(generate()), headers=headers)

# --- HTML UI ---------------------------------------------------------------

ROW = """  <tr>
  <td>{name}</td>
  <td>{repo_cell}</td>
  <td>{unit}</td>
  <td>{status_badge}</td>
  <td>
    <button class="btn" onclick="doSync('{name}')">Sync</button>
    <a class="btn" href="/logs/{unit}" target="_blank">Logs</a>
    <a class="btn" href="/logs/stream/{unit}" target="_blank">Live</a>
  </td>
</tr>
"""

def badge(status):
    if status == "active": return '<span class="b b-ok">● Active</span>'
    if status == "inactive": return '<span class="b b-warn">⚠ Inactive</span>'
    return '<span class="b b-warn">⚠ not found</span>'

def make_repo_cell(repo):
    """
    repo может быть str (URL) или dict со свойствами:
    { "git": "...", "desc": "...", "name": "...", ... }
    """
    try:
        if isinstance(repo, str):
            repo_name = repo.split("/")[-1] or repo
            return f'<a href="{repo}" target="_blank">{repo_name}</a>'
        elif isinstance(repo, dict):
            text = repo.get("git") or repo.get("name") or "repo"
            desc = repo.get("desc", "")
            # не гарантируем, что это URL — просто печатаем текст
            safe = text
            if isinstance(text, str) and (text.startswith("http://") or text.startswith("https://")):
                visible = text.split("/")[-1] or text
                return f'<a href="{text}" target="_blank" title="{desc}">{visible}</a>'
            # иначе просто плейнтекст с подсказкой
            return f'<span title="{desc}">{safe}</span>'
        else:
            return '<span>—</span>'
    except Exception:
        return '<span>—</span>'

@app.get("/")
def index():
    try:
        rows_html_list = []
        for r in projects_table():
            repo_cell = make_repo_cell(r.get("repo"))
            rows_html_list.append(ROW.format(
                name=r.get("name","—"),
                repo_cell=repo_cell,
                unit=r.get("unit","—"),
                status_badge=badge(r.get("status","not-found"))
            ))
        rows_html = "\n".join(rows_html_list)
        t = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>Deniska Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{background:#0b0b0e;color:#eaeaf0;font:16px/1.4 -apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial}}
h1{{display:flex;align-items:center;gap:.5rem}}
h1 .icon{{filter:hue-rotate(70deg)}}
.wrap{{max-width:1100px;margin:24px auto;padding:0 16px}}
.table{{width:100%;border-collapse:collapse;margin-top:12px}}
.table th,.table td{{padding:12px 10px;border-bottom:1px solid #24242a}}
th{{text-align:left;color:#9da3ae;letter-spacing:.02em}}
a{{color:#6aa7ff;text-decoration:none}}
.btn{{background:#111827;border:1px solid #30343c;border-radius:10px;color:#aab0bc;padding:6px 10px;margin-right:6px;cursor:pointer}}
.btn:hover{{border-color:#4b5563;color:#cbd5e1}}
.b{{padding:4px 10px;border-radius:999px;font-size:14px}}
.b-ok{{background:#05290a;color:#36d979}}
.b-warn{{background:#2b2305;color:#f7d154}}
.topline{{display:flex;gap:16px;align-items:center;color:#aab0bc;flex-wrap:wrap}}
.spark{{display:flex;gap:2px;align-items:flex-end;height:28px;min-width:120px}}
.spark div{{width:4px;background:#3b82f6;opacity:.85}}
small{{color:#9da3ae}}
input, .btn-compose{{border-radius:12px;border:1px solid #2a2f39;background:#0f1218;color:#e6e6ee;padding:10px}}
.grid{{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;margin-top:14px}}
@media (max-width: 720px) {{
  .grid{{grid-template-columns:1fr;}}
  .table td:nth-child(2){{word-break:break-all}}
}}
</style>
</head>
<body>
<div class="wrap">
  <h1><span class="icon">🧩</span>Deniska Dashboard</h1>
  <div class="topline">
    <span id="meta">Сервер: {SERVER_NAME} | Обновлено: {t}</span>
    <span id="live">| CPU: <b id="cpu">…</b>% &nbsp; RAM: <b id="ram">…</b>% &nbsp; Uptime: <b id="uptime">…</b></span>
    <div class="spark" id="sparkCPU" title="CPU sparkline"></div>
    <div class="spark" id="sparkRAM" title="RAM sparkline"></div>
    <button class="btn" onclick="massPing()">Ping</button>
  </div>

  <table class="table">
    <thead><tr>
      <th>Проект</th><th>Репозиторий</th><th>Сервис</th><th>Статус</th><th>Действия</th>
    </tr></thead>
    <tbody id="rows">
      {rows_html}
    </tbody>
  </table>

  <div style="border-top:1px solid #24242a;margin-top:14px;padding-top:14px">
    <h3>Создать нового бота</h3>
    <div class="grid">
      <input id="newname" placeholder="новый бот">
      <input id="newsources" placeholder="через пробел: jurist persobi">
      <button class="btn-compose" onclick="compose()">Compose</button>
    </div>
    <small id="composeOut"></small>
  </div>
</div>
<script>
const maxBars = 60;
const sparkCPU = document.getElementById('sparkCPU');
const sparkRAM = document.getElementById('sparkRAM');

function drawSpark(div, arr) {{
  div.innerHTML = '';
  const max = Math.max(1, ...arr);
  arr.forEach(v => {{
    const h = Math.max(2, Math.round((v/max)*28));
    const bar = document.createElement('div');
    bar.style.height = h + 'px';
    div.appendChild(bar);
  }});
}}

async function refreshMetrics() {{
  try {{
    const r = await fetch('/metrics/series'); 
    const j = await r.json();
    const lastCPU = (j.cpu && j.cpu.length) ? j.cpu[j.cpu.length-1] : 0;
    const lastRAM = (j.ram && j.ram.length) ? j.ram[j.ram.length-1] : 0;
    document.getElementById('cpu').textContent = (typeof lastCPU === 'number') ? lastCPU.toFixed(1) : lastCPU;
    document.getElementById('ram').textContent = lastRAM;
    document.getElementById('uptime').textContent = j.uptime || '';
    drawSpark(sparkCPU, (j.cpu || []).slice(-maxBars));
    drawSpark(sparkRAM, (j.ram || []).slice(-maxBars));
  }} catch(e) {{}}
}}
setInterval(refreshMetrics, 1000); refreshMetrics();

async function massPing(){{
  const r = await fetch('/api/ping'); const j = await r.json();
  alert('Ping:\\n' + JSON.stringify(j.ping, null, 2));
}}

async function doSync(name){{
  const r = await fetch('/sync/'+name, {{method:'POST'}});
  const j = await r.json(); alert((j.msg||'done').slice(-2000));
}}

async function compose(){{
  const name = document.getElementById('newname').value.trim();
  const sources = document.getElementById('newsources').value.trim().split(/\\s+/).filter(Boolean);
  const r = await fetch('/compose', {{method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify({{name, sources}})}});
  const j = await r.json();
  document.getElementById('composeOut').textContent = (j.msg||'').slice(-2000);
}}
</script>
</body></html>
"""
    except Exception as e:
        return Response(f"<pre>Render error: {e}</pre>", mimetype="text/html; charset=utf-8"), 500

# --- app run ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=False)
