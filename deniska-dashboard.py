#!/usr/bin/env python3
from flask import Flask, jsonify, render_template_string, send_file
import subprocess, json, os, datetime

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Deniska Dashboard</title>
<style>
body { font-family: sans-serif; background: #111; color: #eee; text-align: center; margin: 0; padding: 0; }
header { background: #222; padding: 12px; display: flex; justify-content: center; gap: 14px; }
button { background: #333; color: #fff; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-weight: 600; }
button:hover { background: #555; }
pre { text-align: left; margin: 20px auto; width: 90%; background: #000; color: #0f0; padding: 10px; border-radius: 8px; overflow-x: auto; }
</style>
</head>
<body>
<header>
  <button onclick="fetchPing()">Ping</button>
  <button onclick="fetchLogs()">Logs</button>
  <button onclick="fetchRestart()">Restart</button>
  <button onclick="window.open('/docs', '_blank')">📘 Docs</button>
</header>
<pre id="output">Загрузка...</pre>
<script>
async function fetchPing(){ const r=await fetch('/ping'); document.getElementById('output').innerText=await r.text(); }
async function fetchLogs(){ const r=await fetch('/logs'); document.getElementById('output').innerText=await r.text(); }
async function fetchRestart(){ const r=await fetch('/restart'); document.getElementById('output').innerText=await r.text(); }
fetchPing();
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/ping')
def ping():
    try:
        out = subprocess.check_output(["bash", "/root/bin/deniska-status.sh"], text=True)
        return out
    except subprocess.CalledProcessError as e:
        return f"Ошибка выполнения: {e}"

@app.route('/logs')
def logs():
    out = subprocess.getoutput("journalctl -u deniska-snapshot.service -n 100 --no-pager")
    return out[-4000:]

@app.route('/restart')
def restart():
    os.system("systemctl restart deniska-snapshot.service")
    return "[✓] Сервис deniska-snapshot.service перезапущен"

@app.route('/docs')
def docs():
    path = "/root/docs/DENISKA_PASSPORT.md"
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
        # простейший HTML-просмотр паспорта
        return f"<html><body style='background:#111;color:#eee;font-family:sans-serif;padding:20px;white-space:pre-wrap;'>{content}</body></html>"
    return "Файл паспорта не найден."

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=18081)
