# wsgi.py — точка входа для gunicorn
# ВНИМАНИЕ: исходный файл называется "deniska-dashboard.py" (с дефисом),
# импорт через __import__ по имени файла недопустим, поэтому используем runpy.

import runpy

# Выполняем скрипт приложения в отдельном пространстве имён и извлекаем app
ns = runpy.run_path("/root/projects/deniska-dashboard/deniska-dashboard.py")
app = ns.get("app")
if app is None:
    raise RuntimeError("Flask app variable 'app' not found in deniska-dashboard.py")
