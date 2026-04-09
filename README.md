# air_monitor_back

Backend сервиса мониторинга и краткосрочного прогнозирования качества воздуха в Норильском промышленном районе.

Проект собирает наблюдения из внешних источников, нормализует временные ряды, строит воспроизводимые датасеты, обучает модели прогноза, запускает ретропроверку и оценку по фактическим данным, а также отдаёт итоговые артефакты во frontend: обзорную аналитику, карту качества воздуха и финальный PDF-отчёт.

## Что умеет backend

- аутентификация пользователей через JWT в `HttpOnly` cookie;
- сбор и хранение наблюдений из `MyCityAir` и городского фона `Plume Labs`;
- агрегация наблюдений в единый часовой ряд;
- сборка `DatasetSnapshot` для воспроизводимого обучения;
- обучение и версионирование моделей прогноза;
- генерация прогнозов и исторический `backtest`;
- оценка прогноза по фактическим наблюдениям;
- запуск одиночных экспериментов и серий экспериментов;
- синхронные, фоновые и отложенные сценарии через Celery;
- snapshot `air-map` для интерактивной карты воздуха;
- итоговый человекочитаемый PDF-отчёт по текущему состоянию системы;
- расширенная Django admin для работы с закрытой БД.

## Технологии

- Python 3.12
- Django 5
- Django Ninja
- PostgreSQL
- Redis
- Celery
- NumPy
- Pandas
- PyTorch
- ReportLab
- Docker Compose
- pytest
- Ruff

## Структура проекта

```text
apps/
  authentication/   login, register, refresh, logout
  common/           base models, middleware, health probes
  monitoring/       observations, datasets, models, forecasts, experiments
  users/            user model and profile API
config/             Django settings, URLs, Celery bootstrap
docker/             dev и deploy compose-слой, Dockerfile, entrypoints
```

Ключевая логика сосредоточена в `apps/monitoring`:

- `api/routers` и `api/schemas` содержат транспортный слой;
- `services` описывает orchestration use-case'ов;
- `selectors` отвечает за чтение и подготовку queryset'ов;
- `ml` содержит подготовку датасетов, train и inference;
- `tasks.py` выносит долгие операции в Celery.

## Основные сущности

- `Observation` — нормализованное наблюдение из внешнего источника.
- `DatasetSnapshot` — зафиксированный срез данных для обучения.
- `ModelVersion` — обученная версия модели с конфигурацией и метриками.
- `ForecastRun` — один запуск генерации прогноза.
- `ForecastEvaluation` — оценка прогноза по фактическим данным.
- `ExperimentRun` — один исследовательский прогон.
- `ExperimentSeries` — группа связанных экспериментальных запусков.

## Что важно в архитектуре

- `DatasetSnapshot` является источником истины для состава признаков, целей и параметров временного окна.
- `ModelVersion` хранит конфигурацию обучения, историю и сводные метрики.
- `ForecastEvaluation` хранит ретропроверку и оценку прогноза по факту.
- Все `POST .../async` endpoint'ы могут стартовать сразу или через `scheduled_for`.
- Генерация прогноза по умолчанию использует активную готовую модель.
- Оценка по факту возможна только после появления наблюдений на весь горизонт прогноза.
- Overview endpoint отдаёт агрегированную аналитику для dashboard frontend.

## API

Swagger:

```text
http://127.0.0.1:8000/api/docs
```

Ключевые группы endpoint'ов:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/users/me`
- `GET /api/monitoring/overview`
- `GET /api/monitoring/overview/report.pdf`
- `GET /api/monitoring/air-map`
- `GET|POST /api/monitoring/observations...`
- `GET|POST /api/monitoring/datasets...`
- `GET|POST /api/monitoring/models...`
- `GET|POST /api/monitoring/forecasts...`
- `GET|POST /api/monitoring/experiments...`
- `GET|POST /api/monitoring/experiment-series...`
- `GET /api/monitoring/tasks/{task_id}`
- `GET|POST /api/monitoring/scheduled-tasks...`

## Карта и итоговый отчёт

- `GET /api/monitoring/air-map` отдаёт snapshot для карты воздуха: последние station-level точки `MyCityAir`, городской фон, границы карты и сводные слои для временной шкалы.
- `GET /api/monitoring/overview/report.pdf` собирает итоговый PDF-отчёт в человекочитаемом формате.
- PDF сейчас оформлен как итог аналитической работы: титульный блок, сводные карточки, схема исследовательского контура, графики, интерпретация прогноза, практическая ценность и выводы.
- Для кириллического PDF backend использует встроенные шрифты `apps/monitoring/assets/fonts/Arial.ttf` и `ArialBold.ttf`, поэтому рендер не зависит от системных шрифтов контейнера.

## Локальный запуск

### Вариант по умолчанию: Docker dev-контур

```bash
make up
make migrate
make create-superuser
```

После запуска доступны:

- backend: `http://127.0.0.1:8000`
- Swagger: `http://127.0.0.1:8000/api/docs`

Dev-контур использует bind mounts, поэтому код backend подхватывается без пересборки `web` контейнера. `worker` и `beat` при изменениях Python-кода обычно нужно перезапустить вручную.

Когда полезно перезапускать сервисы:

- если менялась логика периодических задач, selectors или сервисов, перезапусти как минимум `worker` и `beat`;
- если менялась генерация PDF-отчёта, достаточно перезапустить `web`, потому что именно он отдаёт `/api/monitoring/overview/report.pdf`.

### Локальная установка без Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Этот вариант требует отдельно поднятых PostgreSQL и Redis и обычно нужен для тестов, линтера и локальной отладки.

## Основные команды

### Разработка

```bash
make up
make down
make logs
make shell-web
make migrate
make makemigrations
make create-superuser
```

### Проверки качества

```bash
make lint
make format
make pytest
make check
```

## Deploy

Deploy-контур поднимает backend без bind mounts, публикует `web` только на `127.0.0.1:${APP_PORT}` и рассчитан на совместный запуск с frontend reverse proxy.

Основные команды:

```bash
make deploy-env-init
make deploy-build
make deploy-up
make deploy-up-all FRONTEND_DIR=../air_monitor_front
make deploy-down-all
```

`deploy-up-all` поднимает backend и frontend вместе, но не заменяет явную пересборку образов. При изменениях Dockerfile, зависимостей или frontend bundle перед запуском нужны `make deploy-build` и frontend `make build` либо `make rebuild`.

Подробности вынесены в [DEPLOY.md](DEPLOY.md).

## Конфигурация deploy

Файлы конфигурации создаются из шаблонов:

- `docker/env/app.deploy.example.env`
- `docker/env/db.deploy.example.env`

Минимально нужно заполнить:

- `DJANGO_SECRET_KEY`
- `MYCITYAIR_TOKEN`
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`

Для работы через белый IP также проверь:

- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

## Ограничения предметной области

- Для сборки датасета должно хватать часовых наблюдений под выбранные `input_len_hours` и `forecast_horizon_hours`.
- Модели со статусами `training` и `failed` не используются для прогноза.
- Если в базе нет активной готовой модели, hourly forecast пропускается.
- Оценка прогноза по факту не выполняется, пока наблюдения не дошли до конца прогнозного горизонта.
- Hourly-сбор наблюдений запускается каждый час в `:05` и забирает окно последних `48` часов с агрегацией `Interval1H`.

## Django admin

Так как production-БД не открывается наружу, Django admin используется как основной операторский интерфейс для данных.

В админке доступны:

- регистрация основных monitoring-моделей;
- поиск и фильтрация по ключевым полям;
- сортировки и `date_hierarchy`;
- просмотр JSON-конфигураций и метрик;
- actions для переключения активной модели и отмены запланированных задач.

## Связанные репозитории

Frontend живёт в отдельном репозитории `air_monitor_front`.

## Статус

Проект ориентирован на магистерскую работу и исследовательские сценарии. Кодовая база рассчитана на локальный стенд и серверный Docker deploy, а не на публикацию как универсальный reusable package.
