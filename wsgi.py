#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WSGI-лоадер для Deniska Dashboard.
1) Пытается загрузить Flask-приложение из файла deniska-dashboard.py (с дефисом в имени).
2) Если не получилось — отдаёт минимальный фолбэк с /ping и /nano_index.
"""

import os
import json
import types
import importlib.util
from pathlib import Path
from flask import Flask, jsonify, Response

BASE = Path("/root/projects/deniska-dashboard").resolve()
PRIMARY_FILE = BASE / "deniska-dashboard.py"   # ИМЕННО через дефис
STATE_JSON = Path("/root/secrets/persobi_global_state.json")

def _load_app_from_primary() -> Flask:
    """
    Загружает модуль из файла deniska-dashboard.py и достаёт из него объект Flask `app`.
    """
    if not PRIMARY_FILE.exists():
        raise FileNotFoundError(f"Файл не найден: {PRIMARY_FILE}")

    spec = importlib.util.spec_from_file_location("deniska_dashboard_dyn", str(PRIMARY_FILE))
    if not spec or not spec.loader:
        raise RuntimeError("Не удалось создать spec для deniska-dashboard.py")

    module = importlib.util.module_from_spec(spec)  # type: types.ModuleType
    spec.loader.exec_module(module)                 # выполняем файл как модуль
    candidate = getattr(module, "app", None)
    if candidate is None or not isinstance(candidate, (Flask,)):
        raise RuntimeError("В deniska-dashboard.py не найден Flask `app`")
    return candidate

def _fallback_app() -> Flask:
    """
    Мини-приложение на случай поломок основного.
    Имеет /ping и /nano_index, чтобы nginx и проверки не падали.
    """
    app = Flask("deniska_fallback")

    @app.get("/ping")
    def ping():
        return Response("pong", mimetype="text/plain; charset=utf-8")

    @app.get("/nano_index")
    def nano_index():
        data = {
            "ok": True,
            "state_json_exists": STATE_JSON.exists(),
            "state_keys": [],
            "nano_files": []
        }
        try:
            if STATE_JSON.exists():
                j = json.loads(STATE_JSON.read_text(encoding="utf-8"))
                if isinstance(j, dict):
                    data["state_keys"] = list(j.keys())
        except Exception:
            pass

        # Поищем NANO-доки во всех проектах (как привыкли)
        try:
            roots = [
                Path("/root/projects/deniska-dashboard"),
                Path("/root/projects/jurist"),
                Path("/root/projects/persobi-content"),
                Path("/root/projects/testbot"),
            ]
            out = []
            for r in roots:
                p = r / "docs" / "NANO"
                if p.exists():
                    out += [str(x) for x in p.glob("*.md")]
            data["nano_files"] = out
        except Exception:
            pass

        return jsonify(data)

    @app.get("/")
    def root():
        return Response("Deniska fallback WSGI is alive. Endpoints: /ping, /nano_index",
                        mimetype="text/plain; charset=utf-8")

    return app

# Пытаемся загрузить основное Flask-приложение
try:
    app: Flask = _load_app_from_primary()
except Exception as e:
    # Логически оставляем фолбэк — панель будет отвечать и через nginx
    app = _fallback_app()
