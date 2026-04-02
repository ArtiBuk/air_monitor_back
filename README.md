# air_monitor_back

Backend магистерского проекта по мониторингу и краткосрочному прогнозированию качества воздуха в Норильском промышленном районе.

Проект собирает наблюдения из внешних источников, нормализует их в единый временной ряд, формирует датасеты для обучения, обучает модели прогноза, выполняет backtest и предоставляет API для исследовательской и прикладной работы.

## Назначение проекта

Система решает две задачи:

1. Инженерную.
   Предоставить backend для веб-приложения с аутентификацией, API, очередями задач, хранением данных и воспроизводимым ML-пайплайном.

2. Исследовательскую.
   Дать основу для сравнения моделей, признаков, горизонтов прогноза и серий экспериментов в рамках магистерской работы.

## Текущий функционал

- регистрация, логин, refresh и logout через JWT в `HttpOnly` cookie;
- хранение пользователей и получение текущего профиля;
- сбор наблюдений по качеству воздуха из внешних источников;
- хранение и агрегация наблюдений в PostgreSQL;
- построение `DatasetSnapshot` из наблюдений;
- обучение и версионирование моделей;
- генерация прогноза на выбранный горизонт;
- backtest от исторической точки отсечения;
- оценка прогноза по фактическим данным;
- сравнение моделей, прогнозов, оценок, отдельных экспериментов и серий экспериментов;
- sync и async API-сценарии через Django Ninja и Celery.

## Технологический стек

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

## Архитектура

### Приложения

- `apps/authentication`
  Аутентификация, работа с JWT и cookie-based auth flow.
- `apps/users`
  Кастомный пользователь и API текущего профиля.
- `apps/monitoring`
  Основная предметная область: наблюдения, датасеты, модели, прогнозы, оценки и эксперименты.
- `apps/common`
  Общие базовые модели, middleware и health probes.
- `config`
  Настройки Django, Celery bootstrap, корневой API и URL-маршруты.

### Принципы структуры

Внутри приложений используются такие слои:

- `api`
  Transport-слой: роутеры, схемы и API-утилиты.
- `services`
  Use-case логика и orchestration.
- `selectors`
  Слой чтения и подготовки querysets.
- `models.py`, `managers.py`, `querysets.py`
  ORM и доменная модель.
- `tests`
  Тесты конкретного приложения: `conftest.py`, фабрики, API- и service-тесты.

### Структура `apps/monitoring`

В `monitoring` код разделён по ролям:

- `api/routers`
  Группы endpoint'ов: наблюдения, датасеты, модели, прогнозы, эксперименты, задачи.
- `api/schemas`
  Отдельные схемы для каждого предметного блока.
- `providers`
  Источники внешних данных.
- `ingestion`
  Типы и утилиты нормализации входящих наблюдений.
- `services`
  Основной orchestration: ingestion, training, forecast, evaluation, experiments.
- `ml`
  Работа с датасетом, обучением и inference.
- `tasks.py`
  Celery tasks для долгих операций.

## Доменная модель

### Observation

Нормализованное наблюдение из внешнего источника.

### DatasetSnapshot

Снимок датасета для обучения:

- окно входа `input_len_hours`;
- горизонт прогноза `forecast_horizon_hours`;
- признаки и целевые переменные;
- metadata о сборке датасета;
- бинарный `npz` payload со split-данными.

### ModelVersion

Версия обученной модели:

- привязка к датасету;
- training config;
- feature и target names;
- train/test метрики;
- история обучения;
- checkpoint модели;
- статус и флаг активной версии.

### ForecastRun

Один запуск генерации прогноза.

### ForecastEvaluation

Оценка качества конкретного прогноза по фактическим наблюдениям.

### ExperimentRun

Один полный исследовательский запуск:

- сбор датасета;
- обучение модели;
- optional backtest;
- optional evaluation;
- конфигурация запуска;
- компактная сводка результата.

### ExperimentSeries

Группа `ExperimentRun` для одной исследовательской кампании.

## Источники истины в данных и метриках

Чтобы данные и результаты не дублировались в нескольких местах, в проекте приняты такие правила:

- структура датасета хранится в `DatasetSnapshot`;
- training config и train/test метрики хранятся в `ModelVersion`;
- backtest и evaluation метрики хранятся в `ForecastEvaluation`;
- `ExperimentRun` хранит конфигурацию orchestration и краткую сводку;
- `ExperimentSeries` хранит общую конфигурацию серии и агрегированную summary.

Это значит, что полные train-метрики нужно читать из `ModelVersion.metrics`, а полные backtest-метрики из `ForecastEvaluation.metrics`.

## API

Swagger:

```text
http://localhost:8000/api/docs
```

### Auth

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`

### Users

- `GET /api/users/me`

### Monitoring

Наблюдения:

- `GET /api/monitoring/observations`
- `POST /api/monitoring/observations/collect`
- `POST /api/monitoring/observations/collect/async`

Датасеты:

- `GET /api/monitoring/datasets`
- `GET /api/monitoring/datasets/{dataset_snapshot_id}`
- `POST /api/monitoring/datasets/build`
- `POST /api/monitoring/datasets/build/async`

Модели:

- `GET /api/monitoring/models`
- `GET /api/monitoring/models/active`
- `GET /api/monitoring/models/{model_version_id}`
- `GET /api/monitoring/models/compare`
- `GET /api/monitoring/models/leaderboard`
- `POST /api/monitoring/models/train`
- `POST /api/monitoring/models/train/async`

Прогнозы:

- `GET /api/monitoring/forecasts`
- `GET /api/monitoring/forecasts/latest`
- `GET /api/monitoring/forecasts/{forecast_run_id}`
- `GET /api/monitoring/forecasts/compare`
- `POST /api/monitoring/forecasts/generate`
- `POST /api/monitoring/forecasts/generate/async`
- `POST /api/monitoring/forecasts/backtest`

Оценки прогнозов:

- `GET /api/monitoring/forecasts/evaluations`
- `GET /api/monitoring/forecasts/evaluations/compare`
- `GET /api/monitoring/forecasts/{forecast_run_id}/evaluation`
- `POST /api/monitoring/forecasts/{forecast_run_id}/evaluate`

Эксперименты:

- `GET /api/monitoring/experiments`
- `GET /api/monitoring/experiments/{experiment_run_id}`
- `GET /api/monitoring/experiments/compare`
- `POST /api/monitoring/experiments/run`
- `POST /api/monitoring/experiments/run/async`

Серии экспериментов:

- `GET /api/monitoring/experiment-series`
- `GET /api/monitoring/experiment-series/{series_id}`
- `GET /api/monitoring/experiment-series/{series_id}/runs`
- `GET /api/monitoring/experiment-series/{series_id}/report`
- `GET /api/monitoring/experiment-series/compare`
- `GET /api/monitoring/experiment-series/reports/compare`
- `POST /api/monitoring/experiment-series`

Статус фоновой задачи:

- `GET /api/monitoring/tasks/{task_id}`

Запланированные задачи:

- `GET /api/monitoring/scheduled-tasks`
- `GET /api/monitoring/scheduled-tasks/{scheduled_task_id}`
- `POST /api/monitoring/scheduled-tasks/{scheduled_task_id}/cancel`

## Отложенные задачи

Все `POST .../async` endpoint'ы поддерживают опциональное поле `scheduled_for`.

- если `scheduled_for` не передан, задача сразу ставится в очередь Celery;
- если `scheduled_for` передан, backend создаёт `ScheduledMonitoringTask`, сохраняет payload и планирует запуск на указанное время;
- отменить можно только задачу в статусе `scheduled`.

Пример отложенного запуска:

```json
{
  "input_len_hours": 72,
  "forecast_horizon_hours": 24,
  "scheduled_for": "2026-04-03T06:00:00Z"
}
```

## Контракты `experiments`

Запуск эксперимента использует вложенные блоки `dataset`, `training` и `backtest`.

Пример:

```json
{
  "name": "baseline-exp",
  "series_id": "uuid-or-null",
  "dataset": {
    "input_len_hours": 72,
    "forecast_horizon_hours": 24,
    "feature_columns": ["plume_pm25", "plume_pm10"],
    "target_columns": ["plume_pm25"]
  },
  "training": {
    "epochs": 50,
    "batch_size": 16,
    "lr": 0.001,
    "weight_decay": 0.0001,
    "patience": 5,
    "seed": 42
  },
  "backtest": {
    "generated_from_timestamp_utc": "2026-03-05T23:00:00Z"
  }
}
```

Конфигурация серии экспериментов хранится как typed-структура и тоже может содержать `dataset`, `training`, `backtest` и дополнительную metadata.

## Локальный запуск

### Требования

- Docker
- Docker Compose
- Python 3.12 и локальная `.venv` для запуска тестов и линтера

### Основные команды

```bash
make help
make build
make up
make ps
make logs
make migrate
make down
```

### Команды разработки

```bash
make lint
make format
make pytest
make pytest-create-db
make check
```

`make check` запускает базовую проверку проекта: линтер и тесты.

## Docker-стек

В dev-стеке используются сервисы:

- `web`
- `worker`
- `beat`
- `postgres`
- `redis`

Что важно:

- `make up` не делает принудительную пересборку;
- пересборка вынесена в `make build` и `make rebuild`;
- код примонтирован в контейнеры через bind mounts;
- `web` работает в dev-режиме с автоматическим подхватом изменений Python-кода;
- `worker` и `beat` при изменении кода нужно перезапускать вручную.

## Аутентификация

- access и refresh токены хранятся в `HttpOnly` cookie;
- защищённые ручки умеют читать токены и из cookie, и из `Authorization: Bearer ...`;
- `refresh` и `logout` могут отрабатывать с пустым JSON body, если refresh-токен уже есть в cookie.

## Async-сценарии

Через Celery вынесены долгие операции:

- сбор наблюдений;
- построение датасета;
- обучение модели;
- генерация прогноза;
- полный `ExperimentRun`.

Статус фоновой задачи запрашивается через:

```text
GET /api/monitoring/tasks/{task_id}
```

## Тестирование

Тесты организованы по приложениям. Для `monitoring` есть:

- API-тесты;
- service-тесты;
- фабрики и фикстуры в `apps/monitoring/tests`.

Тестовая база:

- SQLite в директории `.testdb/`;
- `pytest` запускается с `--reuse-db`;
- Celery в тестах переведён на in-memory broker/backend.

## Качество кода

- `ruff` используется для lint и format;
- локальные git hooks лежат в `.githooks`;
- подключение hooks выполняется командой `make hooks-install`.

## Management commands

```bash
python manage.py collect_observations
python manage.py generate_forecast
```

## Текущее состояние

На текущем этапе backend закрывает основную инженерную и исследовательскую часть:

- ingestion наблюдений;
- подготовку датасета;
- обучение и хранение моделей;
- прогноз;
- backtest и evaluation;
- отдельные эксперименты и серии экспериментов.

Следующий крупный этап уже не backend-инфраструктурный, а прикладной:

- работа с реальными данными НПР;
- подбор признаков и гиперпараметров;
- анализ качества модели;
- подготовка фронтенда для демонстрации результатов.
