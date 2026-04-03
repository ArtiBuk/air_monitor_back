# air_monitor_back

Backend сервиса мониторинга и краткосрочного прогнозирования качества воздуха в Норильском промышленном районе.

Проект отвечает за сбор наблюдений, нормализацию временных рядов, подготовку датасетов, обучение моделей, генерацию прогнозов, ретропроверку, оценку по фактическим данным и orchestration исследовательских прогонов.

## Возможности

- аутентификация пользователей через JWT в `HttpOnly` cookie;
- сбор и хранение наблюдений из внешних источников;
- агрегация наблюдений в единый часовой ряд;
- сборка `DatasetSnapshot` для воспроизводимого обучения;
- обучение и версионирование моделей прогноза;
- генерация прогнозов и исторический `backtest`;
- оценка прогноза по фактическим наблюдениям;
- запуск одиночных экспериментов и исследовательских серий;
- синхронные, фоновые и отложенные сценарии через Celery.

## Технологии

- Python 3.12
- Django 5
- Django Ninja
- PostgreSQL
- Redis
- Celery
- Gunicorn
- NumPy
- Pandas
- PyTorch
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

Ключевая предметная логика живёт в `apps/monitoring`:

- `api/routers` и `api/schemas` содержат транспортный слой;
- `services` описывает use-case orchestration;
- `selectors` отвечает за чтение и подготовку querysets;
- `ml` содержит подготовку датасета, train и inference;
- `tasks.py` выносит долгие операции в Celery.

## Основные сущности

- `Observation` — нормализованное наблюдение из внешнего источника.
- `DatasetSnapshot` — зафиксированный срез данных для обучения.
- `ModelVersion` — обученная версия модели с конфигурацией и метриками.
- `ForecastRun` — один запуск генерации прогноза.
- `ForecastEvaluation` — оценка прогноза по фактическим данным.
- `ExperimentRun` — полный исследовательский прогон.
- `ExperimentSeries` — группа связанных экспериментальных запусков.

## Что важно в архитектуре

- `DatasetSnapshot` используется как источник истины для состава признаков, целей и параметров временного окна.
- `ModelVersion` хранит training config, историю обучения и train/test метрики.
- `ForecastEvaluation` хранит метрики ретропроверки и оценки по факту.
- Все `POST .../async` endpoint'ы умеют работать либо сразу через очередь, либо отложенно через поле `scheduled_for`.
- Генерация прогноза по умолчанию опирается на активную готовую модель.
- Оценка прогноза по факту возможна только после того, как в системе появились наблюдения на весь горизонт прогноза.

## API

Swagger:

```text
http://127.0.0.1:8000/api/docs
```

Основные группы endpoint'ов:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/users/me`
- `GET|POST /api/monitoring/observations...`
- `GET|POST /api/monitoring/datasets...`
- `GET|POST /api/monitoring/models...`
- `GET|POST /api/monitoring/forecasts...`
- `GET|POST /api/monitoring/experiments...`
- `GET|POST /api/monitoring/experiment-series...`
- `GET /api/monitoring/tasks/{task_id}`
- `GET|POST /api/monitoring/scheduled-tasks...`

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

### Локальная установка без Docker

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Этот вариант требует отдельно поднятых PostgreSQL и Redis и обычно нужен только для запуска тестов, линтера или точечной отладки.

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

Deploy-контур поднимает backend без bind mounts, публикует `web` только на `127.0.0.1:${APP_PORT}` и рассчитан на запуск вместе с frontend reverse proxy.

Основные команды:

```bash
make deploy-env-init
make deploy-build
make deploy-up
make deploy-up-all FRONTEND_DIR=../air_monitor_front
make deploy-down-all
```

Подробная инструкция для сервера вынесена в [DEPLOY.md](DEPLOY.md).

## Конфигурация deploy

Файлы конфигурации создаются из шаблонов:

- `docker/env/app.deploy.example.env`
- `docker/env/db.deploy.example.env`

Минимум, что нужно заполнить перед deploy:

- `DJANGO_SECRET_KEY`
- `MYCITYAIR_TOKEN`
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`

Для работы через белый IP также проверь:

- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

## Технические ограничения предметной области

- Для сборки датасета должно хватать часовых наблюдений под выбранные `input_len_hours` и `forecast_horizon_hours`.
- Модели со статусами `training` и `failed` не подходят для прогноза.
- Если в базе нет активной готовой модели, hourly forecast пропускается.
- Оценка прогноза по факту не выполняется, пока фактические наблюдения не дошли до конца прогнозного горизонта.

## Связанные репозитории

Frontend интерфейс живёт в отдельном репозитории `air_monitor_front`.

## Статус

Проект ориентирован на магистерскую работу и исследовательские сценарии. Кодовая база рассчитана на локальный стенд и серверный Docker deploy, а не на публикацию как универсальный reusable package.
