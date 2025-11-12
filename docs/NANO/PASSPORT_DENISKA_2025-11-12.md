# Паспорт системы — «Дениска Дашборд»
Дата: 2025-11-12

## 1) Назначение
Единая панель мониторинга и оперативных действий по проектам (сервисы, снапшоты, Git-состояние, логи).

## 2) Хранилища и ключевые пути
- Глобальная карта проектов (источник правды): `/root/secrets/persobi_global_state.json`
- Репозиторий панели: `/root/projects/deniska-dashboard` (origin: `git@github.com:Alexandr123456098/deniska-dashboard.git`)
- Папка PASSPORT/NANO: `/root/projects/deniska-dashboard/docs/NANO/`
- STATE агрегат: `/root/projects/deniska-dashboard/docs/STATE.json` (генерируется утилитами Дениски/скриптами)
- Снапшоты (общая корзина): `/root/snapshots/`
  - Дениска панель: `/root/snapshots/deniska_*.tgz`
  - Persobi Content Factory: `/root/snapshots/content_factory_*.tgz`
  - Antishtraf: `/root/snapshots/antishtraf_*.tgz`
- Веб-доступ к панели: `nginx:8081` → Дениска (локально `/api/services`, `/metrics`, `/ping`)
  - Базовая авторизация: пользователь `alex` (пароль зафиксирован в приватных заметках)
- Локальные пути проектов:
  - Persobi Content: `/opt/content_factory`
  - Antishtraf: `/opt/antishtraf`
  - Jurist 1.5 PRO: `/root/projects/jurist`

## 3) Репозитории и синхронизация
- `deniska-dashboard` → `git@github.com:Alexandr123456098/deniska-dashboard.git` (ветка: `main`)
- `persobi-content` → `git@github.com:Alexandr123456098/persobi-content.git` (ветка: `main`, релиз-тег: `release-2025-11-12_0433`)
- `antishtraf` → `git@github.com:Alexandr123456098/antishtraf.git` (ветка: `main`)
- `jurist-autosave` → `git@github.com:Alexandr123456098/jurist-autosave.git` (ветка: `main`)

Политика: коммиты из рабочих каталогов с автоснапшотами; теги на стабильные состояния; автосохранения через cron/скрипты Дениски (см. раздел 8).

## 4) systemd-сервисы (состояние на 2025-11-12)
- `deniska-dashboard.service` — панель (Flask+gunicorn) — **enabled/active**
- `content-factory.service` — Persobi Content Bot — **enabled/active**
- `antishtraf.service` — Antishtraf MVP — **enabled/active**
- `jurist.service` — Юрист 1.5 PRO — **enabled/active**

Путь к юнитам: `/etc/systemd/system/<unit>.service` (+ drop-ins в `/etc/systemd/system/<unit>.service.d/`).

## 5) Текущее состояние (оперативная сводка)
API панели отдаёт JSON по `http://127.0.0.1:18081/api/services`. На момент фиксации:
- все 4 юнита **enabled** и **running**
- Persobi Content регулярно пишет OK-события генерации (`replicate(text) OK`, fallback offline для image)
- Дениска перезапускается корректно, ворнинг по `StartLimitIntervalSec` устранить переносом в секцию `[Unit]` (см. чек-лист ниже)

## 6) Контрольные файлы
- Паспорт (этот документ): `/root/projects/deniska-dashboard/docs/NANO/PASSPORT_DENISKA_2025-11-12.md`
- Агрегированный `STATE.json`: `/root/projects/deniska-dashboard/docs/STATE.json`
- Глобальная карта: `/root/secrets/persobi_global_state.json`
- Снапшоты проектов: `/root/snapshots/*.tgz`
- Логи сервисов: `journalctl -u <unit> -n 200 -f`

## 7) Восстановление системы (сценарий DR)
1. Установить зависимости и склонировать проекты в те же пути:
   - `/root/projects/deniska-dashboard`
   - `/opt/content_factory`
   - `/root/projects/antishtraf`
   - `/root/projects/jurist`
2. Восстановить `/root/secrets/persobi_global_state.json`.
3. Разместить .env/секреты проектов вне Git (внутренние пути по проектам), права `600`.
4. Развернуть юниты:
   - `deniska-dashboard.service`
   - `content-factory.service`
   - `antishtraf.service`
   - `jurist.service`
5. `systemctl daemon-reload` → `systemctl enable --now <каждый юнит>`.
6. Проверить панель: `nginx:8081` → `/api/services` и `/metrics`.
7. При необходимости развернуть проекты из снапшотов `/root/snapshots/*.tgz` (последние файлы по датам).

## 8) Гарантии преемственности (что увидит «следующий Дениска/Петя»)
- Панель читает `/root/secrets/persobi_global_state.json` и отображает проекты/юниты в таблице.
- `STATE.json` фиксирует агрегированную сводку (глобальная карта + `/api/services`) — точка входа для быстрой инициализации.
- Git-репозитории привязаны (origin=GitHub), стабильные релизы помечаются тегами (`release-YYYY-MM-DD_*`).
- Снапшоты в `/root/snapshots/` позволяют поднять рабочие директории «как есть».
- Чек-лист проверок ниже исключает дребезг и «забытые» шаги.

## 9) Чек-лист операционных проверок
- `systemctl is-enabled deniska-dashboard.service content-factory.service antishtraf.service jurist.service` → все `enabled`
- `systemctl is-active ...` → все `active`
- `journalctl -u deniska-dashboard.service -n 100 -f` → без ошибок Flask/gunicorn
- `curl -s http://127.0.0.1:18081/api/services | jq .` → валидный JSON с 4 строчками
- Дениска юнит: ключи старт-лимита в `[Unit]` (а не в `[Service]`):
  - `StartLimitIntervalSec=`
  - `StartLimitBurst=`

## 10) Сводка по проектам
### Deniska Dashboard
- Путь: `/root/projects/deniska-dashboard`
- Сервис: `deniska-dashboard.service`
- Назначение: UI-панель состояний, логов, снапшотов и быстрых действий
- Origin: `git@github.com:Alexandr123456098/deniska-dashboard.git`

### Persobi Content Factory
- Путь: `/opt/content_factory`
- Сервис: `content-factory.service`
- Кнопки UI бота: `again, sora2_go, photo_help, video_help`
- Последние снапшоты: `/root/snapshots/content_factory_*.tgz`
- Origin: `git@github.com:Alexandr123456098/persobi-content.git`
- Текущий релиз-тег: `release-2025-11-12_0433`

### Antishtraf
- Путь: `/opt/antishtraf`
- Сервис: `antishtraf.service`
- HTTP порт: `18085` (локально)
- Снапшоты: `/root/snapshots/antishtraf_*.tgz`
- Repo (рабочая копия): `/root/projects/antishtraf` (origin: `git@github.com:Alexandr123456098/antishtraf.git`)

### Jurist 1.5 PRO
- Путь: `/root/projects/jurist`
- Сервис: `jurist.service`
- Origin: `git@github.com:Alexandr123456098/jurist-autosave.git`

## 11) История и релизы
- Persobi Content: `release-2025-11-12_0433` — стабильный слепок после очистки истории и настройки защит.
- Рекомендуемая политика: теги на стабильные точки всех проектов в момент снапшотов Дениски.

— Конец паспорта —
