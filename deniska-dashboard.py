#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, subprocess, shlex, html, mimetypes
from pathlib import Path
from datetime import datetime
from flask import Flask, Response, jsonify, request, send_file

app = Flask(__name__)

# Карта известных репозиториев/проектов (расширяемая)
REPOS = [
    {"name": "deniska",          "unit": "deniska-dashboard.service", "path": "/root/projects/deniska-dashboard"},
    {"name": "persobi-content",  "unit": "content-factory.service",   "path": "/opt/content_factory"},
    {"name": "netshtrafa",       "unit": "netshtrafa.service",        "path": "/root/projects/netshtrafa"},
    {"name": "jurist",           "unit": "jurist.service",            "path": "/root/projects/jurist"},
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
                for k in ["status", "branch", "origin", "dirty"]:
                    item[k] = data.get(k, item[k])
        except Exception:
            pass
        rows.append(item)
    return rows

def collect_status_quick():
    # Пытаемся взять готовый JSON от скрипта, иначе — STATE.json
    try:
        cp = run("bash /root/bin/deniska-status.sh", timeout=6.0)
        if cp.returncode == 0:
            data = json.loads(cp.stdout.strip())
            rows = data.get("rows") or []
            byname = {r["name"]: r for r in rows if isinstance(r, dict) and "name" in r}
            out = []
            for r in REPOS:
                base = {"name": r["name"], "unit": r["unit"], "path": r["path"],
                        "status": "unknown", "branch": "-", "origin": "-", "dirty": "-"}
                upd = byname.get(r["name"]) or {}
                for k, v in upd.items():
                    base[k] = v
                out.append(base)
            return out
    except Exception:
        pass
    return read_state_files()

# ---------- Базовые эндпойнты ----------
@app.route("/ping")
def ping():
    return _no_store(jsonify({"ok": True}))

@app.route("/api/services")
def api_services():
    rows = collect_status_quick()
    resp = jsonify({"rows": rows})
    return _no_store(resp)

@app.route("/logs")
def logs():
    unit = request.args.get("unit", "deniska-dashboard.service")
    try:
        cp = run(f"journalctl -u {shlex.quote(unit)} -n 200 --no-pager", timeout=3.5)
        body = cp.stdout[-10000:] if cp.stdout else cp.stderr
        body = html.escape(body)
    except Exception as e:
        body = "error: " + html.escape(str(e))
    html_page = (
        "<pre style='background:#111;color:#eee;padding:16px;white-space:pre-wrap'>"
        + body + "</pre>"
    )
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
        "<html><body style='background:#111;color:#eee;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;"
        "padding:20px;white-space:pre-wrap;'>" + text + "</body></html>"
    )
    return Response(html_page, mimetype="text/html")

# ---------- NANO: индекс, просмотр, страница ----------
def list_nano_for_project(project_path: str):
    base = Path(project_path) / "docs" / "NANO"
    files = []
    if base.exists() and base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file():
                rel = p.relative_to(base).as_posix()
                try:
                    st = p.stat()
                    files.append({
                        "name": p.name,
                        "relpath": rel,
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                    })
                except Exception:
                    files.append({"name": p.name, "relpath": rel, "size": 0, "mtime": 0})
    return files

@app.route("/nano_index")
def nano_index():
    out = []
    for r in REPOS:
        out.append({
            "project": r["name"],
            "path": r["path"],
            "items": list_nano_for_project(r["path"])
        })
    return _no_store(jsonify({"at": datetime.now().isoformat(), "projects": out}))

def safe_join(base: Path, rel: str) -> Path:
    # Безопасное соединение с проверкой выхода из каталога
    relp = Path(rel)
    cand = (base / relp).resolve()
    if str(cand).startswith(str(base.resolve())):
        return cand
    raise ValueError("bad path")

@app.route("/nano_view")
def nano_view():
    project = request.args.get("project", "")
    rel = request.args.get("path", "")
    proj = next((r for r in REPOS if r["name"] == project), None)
    if not proj:
        return Response("project not found", status=404)
    base = Path(proj["path"]) / "docs" / "NANO"
    try:
        target = safe_join(base, rel)
        if not target.exists() or not target.is_file():
            return Response("file not found", status=404)
        text = target.read_text(encoding="utf-8", errors="replace")
        esc = html.escape(text)
        title = html.escape(f"{project} — {rel}")
        page = (
            "<html><head><meta charset='utf-8'/>"
            "<title>" + title + "</title>"
            "<style>"
            "body{background:#111;color:#eee;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0}"
            ".top{display:flex;gap:12px;padding:14px;background:#1b1b1b;position:sticky;top:0;border-bottom:1px solid #333}"
            ".btn{background:#2a2a2a;border:1px solid #3a3a3a;border-radius:10px;padding:8px 14px;text-decoration:none;color:#eee}"
            ".btn:hover{background:#333}"
            "pre{padding:16px;margin:0;white-space:pre-wrap}"
            "</style></head><body>"
            "<div class='top'>"
            "<a class='btn' href='/nano'>← NANO</a>"
            "<a class='btn' href='/nano_raw?project="+ html.escape(project) +"&path="+ html.escape(rel) +"' target='_blank'>⬇ raw</a>"
            "</div>"
            "<pre>" + esc + "</pre>"
            "</body></html>"
        )
        return Response(page, mimetype="text/html")
    except Exception as e:
        return Response("error: " + html.escape(str(e)), status=500)

@app.route("/nano_raw")
def nano_raw():
    project = request.args.get("project", "")
    rel = request.args.get("path", "")
    proj = next((r for r in REPOS if r["name"] == project), None)
    if not proj:
        return Response("project not found", status=404)
    base = Path(proj["path"]) / "docs" / "NANO"
    try:
        target = safe_join(base, rel)
        if not target.exists() or not target.is_file():
            return Response("file not found", status=404)
        # отдаём как text/plain с корректным mimetype
        mime = mimetypes.guess_type(target.name)[0] or "text/plain"
        return send_file(str(target), mimetype=mime, as_attachment=False, download_name=target.name)
    except Exception as e:
        return Response("error: " + html.escape(str(e)), status=500)

# ---------- Главная HTML ----------
INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Deniska Dashboard</title>
<style>
 body{background:#0f1115;color:#e7e7ea;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0}
 .top{display:flex;gap:12px;padding:14px;background:#12141b;position:sticky;top:0;border-bottom:1px solid #2a2f3a}
 .btn{background:#1a1f2a;border:1px solid #2a3242;border-radius:12px;padding:8px 14px;cursor:pointer;color:#e7e7ea}
 .btn:hover{background:#202738}
 .badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;margin-left:8px}
 .ok{background:#0f2b1a;color:#89f0a1;border:1px solid #1c3b28}
 .bad{background:#2b0f1a;color:#ff9aba;border:1px solid #3b1c28}
 table{width:100%;border-collapse:collapse;margin:16px}
 th,td{padding:10px;border-bottom:1px solid #2a2f3a}
 .mono{font-family:ui-monospace, SFMono-Regular, Menlo, monospace}
 .pill{padding:2px 8px;border-radius:999px;background:#171a22;border:1px solid #2a2f3a}
 h1{font-size:18px;font-weight:600;margin:16px}
</style>
</head>
<body>
 <div class="top">
   <button class="btn" onclick="doPing()">Ping</button>
   <button class="btn" onclick="openLogs()">Logs</button>
   <button class="btn" onclick="doRestart()">Restart</button>
   <a class="btn" href="/docs" target="_blank">📘 Docs</a>
   <a class="btn" href="/nano" target="_self">📗 NANO</a>
 </div>
 <h1 id="ttl">Готово</h1>
 <div id="status" class="mono" style="padding:12px">Загрузка…</div>
 <div id="table"></div>
<script>
 async function fetchJSON(url){
   const r = await fetch(url, {cache:'no-store'});
   if(!r.ok) throw new Error('HTTP '+r.status);
   return await r.json();
 }
 function esc(s){return (s||'').toString().replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
 async function load(){
   try{
     document.getElementById('status').textContent='Загрузка…';
     const data = await fetchJSON('/api/services');
     const rows = data.rows||[];
     let html = '<table><thead><tr><th>Проект</th><th>Unit</th><th>Статус</th><th>Ветка</th><th>Origin</th><th>Dirty</th><th>Путь</th></tr></thead><tbody>';
     for(const r of rows){
       const ok = (r.status||'').toLowerCase()==='active';
       html += '<tr>'
         + '<td>'+esc(r.name||'')+'</td>'
         + '<td><span class="pill">'+esc(r.unit||'')+'</span></td>'
         + '<td>'+(ok?'<span class="badge ok">Active</span>':'<span class="badge bad">'+esc(r.status||'?')+'</span>')+'</td>'
         + '<td>'+esc(r.branch||'-')+'</td>'
         + '<td>'+esc(r.origin||'-')+'</td>'
         + '<td>'+esc(r.dirty||'-')+'</td>'
         + '<td class="mono">'+esc(r.path||'')+'</td>'
         + '</tr>';
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

NANO_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>NANO Archive</title>
<style>
 body{background:#0f1115;color:#e7e7ea;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0}
 .top{display:flex;gap:12px;padding:14px;background:#12141b;position:sticky;top:0;border-bottom:1px solid #2a2f3a}
 .btn{background:#1a1f2a;border:1px solid #2a3242;border-radius:12px;padding:8px 14px;text-decoration:none;color:#e7e7ea}
 .btn:hover{background:#202738}
 .card{margin:16px;border:1px solid #2a2f3a;border-radius:14px;background:#111521}
 .card h2{margin:0;padding:12px 16px;border-bottom:1px solid #2a2f3a;font-size:16px}
 .list{padding:8px 16px 16px 16px}
 .item{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px dashed #232a36}
 .muted{opacity:.75}
 .mono{font-family:ui-monospace, SFMono-Regular, Menlo, monospace}
</style>
</head>
<body>
 <div class="top">
   <a class="btn" href="/">← Dashboard</a>
   <span class="btn">📗 NANO</span>
 </div>
 <div id="root"></div>
<script>
 function esc(s){return (s||'').toString().replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'gt;'}[c]))}
 async function fetchJSON(url){ const r=await fetch(url,{cache:'no-store'}); if(!r.ok) throw new Error('HTTP '+r.status); return await r.json(); }
 function formatTS(ts){ try{ const d=new Date(ts*1000); return d.toLocaleString(); }catch(_){ return '-'; } }
 async function load(){
   const data = await fetchJSON('/nano_index');
   const projects = data.projects||[];
   let html='';
   for(const p of projects){
     html += '<div class="card"><h2>'+esc(p.project)+' — '+esc(p.path)+'</h2><div class="list">';
     if(!p.items || p.items.length===0){
       html += '<div class="muted">Файлов нет (docs/NANO)</div>';
     }else{
       for(const it of p.items){
         const url = '/nano_view?project='+encodeURIComponent(p.project)+'&path='+encodeURIComponent(it.relpath);
         html += '<div class="item"><div>'
              + '<a class="mono" href="'+url+'" target="_blank">'+esc(it.relpath)+'</a>'
              + '</div><div class="muted">'+(it.size||0)+' B · '+esc(formatTS(it.mtime))+'</div></div>';
       }
     }
     html += '</div></div>';
   }
   document.getElementById('root').innerHTML = html;
 }
 load();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html")

@app.route("/nano")
def nano_page():
    return Response(NANO_HTML, mimetype="text/html")

if __name__ == "__main__":
    # Разворачиваем только на 0.0.0.0:18081 (systemd управляет жизненным циклом)
    app.run(host="0.0.0.0", port=18081)
