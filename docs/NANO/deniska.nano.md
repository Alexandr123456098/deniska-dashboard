# Deniska Dashboard — NANO эталон

## Пути и состав
- Код: /root/projects/deniska-dashboard/deniska-dashboard.py
- Venv: /root/projects/deniska-dashboard/venv
- Юнит: /etc/systemd/system/deniska-dashboard.service
- Nginx прокси: 127.0.0.1:8081 (basic-auth: alex/FL21010808 → к внешнему :8081)
- Flask порт: 0.0.0.0:18081

## Юнит (эталон)
/etc/systemd/system/deniska-dashboard.service
--------------------------------------------
[Unit]
Description=Deniska Dashboard (Flask UI)
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/root/projects/deniska-dashboard
Environment=PYTHONUNBUFFERED=1
ExecStart=/root/projects/deniska-dashboard/venv/bin/python deniska-dashboard.py
Restart=on-failure
RestartSec=3s

[Install]
WantedBy=multi-user.target

## Команды проверки
systemctl daemon-reload
systemctl restart deniska-dashboard.service
systemctl status deniska-dashboard.service --no-pager
ss -ltnp | grep 18081 || true
curl -fsS http://127.0.0.1:18081/ping && echo
curl -u alex:FL21010808 -fsS http://127.0.0.1:8081/ping && echo
curl -u alex:FL21010808 -fsS http://127.0.0.1:8081/nano_index | jq -c '.projects|map({p:.project,c:(.items|length)})'

## Снапшот
bash /root/bin/deniska-snapshot.sh

## Чёрный список
- f-string с обратной косой в выражении → SyntaxError (исправлено).
- /nano_index должен отвечать и на 18081, и на 8081 (через nginx).

## Быстрый чек-лист
1) Юнит active (running)
2) 18081 слушает
3) 8081 /ping OK
4) /nano_index отдаёт список
