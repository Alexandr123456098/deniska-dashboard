# -*- coding: utf-8 -*-
"""
Аварийный WSGI для Дениски.
Логика:
1) Пытаемся импортировать готовый Flask app:
   - from deniska_dashboard import app
   - import app (из app.py в корне проекта)
2) Если не нашли — поднимаем минимальное приложение со /ping и /nano_index,
   чтобы убрать 502 и дать панельке жить.
"""

import os
import json
import pathlib
from typing import List

app = None

# 1) Попытки импорта «нормального» приложения
try:
    # Вариант: пакет проекта (рекомендовано для продакшена)
    from deniska_dashboard import app as app  # type: ignore
except Exception:
    try:
        # Вариант: файл app.py в корне проекта
        import importlib
        _app_mod = importlib.import_module("app")
        app = getattr(_app_mod, "app", None)
    except Exception:
        app = None

# 2) Фолбэк — минимальное приложение
if app is None:
    from flask import Flask, jsonify

    app = Flask(__name__)

    PROJECTS_ROOT = pathlib.Path("/root/projects")
    STATE_PATH = pathlib.Path("/root/secrets/persobi_global_state.json")

    def _nano_files() -> List[str]:
        files: List[str] = []
        if PROJECTS_ROOT.exists():
            for p in PROJECTS_ROOT.glob("*/docs/NANO/*.md"):
                try:
                    files.append(str(p))
                except Exception:
                    pass
        return sorted(files)

    @app.get("/ping")
    def ping():
        return "pong", 200

    @app.get("/nano_index")
    def nano_index():
        data = {
            "ok": True,
            "nano_files": _nano_files(),
            "state_json_exists": STATE_PATH.exists(),
        }
        # Опционально: вернуть верхние ключи карты проектов, если файл есть
        if STATE_PATH.exists():
            try:
                with STATE_PATH.open("r", encoding="utf-8") as f:
                    j = json.load(f)
                if isinstance(j, dict):
                    data["state_keys"] = sorted(list(j.keys()))
            except Exception as e:
                data["state_error"] = str(e)
        return jsonify(data), 200

    @app.get("/")
    def index():
        return (
            "Deniska fallback WSGI is alive. Endpoints: /ping, /nano_index",
            200,
        )

# Важно для gunicorn: переменная app должна существовать
assert app is not None, "WSGI app is not initialized"
