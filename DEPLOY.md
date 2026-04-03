# Как поднять проект на сервере

Ниже короткая инструкция, если нужно просто забрать оба репозитория и запустить всё на машине.

## Что должно быть готово заранее

- На сервере установлен `Docker` и работает `docker compose`.
- Снаружи открыт порт `80`.
- Есть белый IP сервера.

## 1. Склонировать репозитории

Удобнее всего положить их рядом:

```bash
git clone <backend-repo> air_monitor_back
git clone <frontend-repo> air_monitor_front
```

Дальше работаем из backend-репозитория:

```bash
cd air_monitor_back
```

## 2. Создать env-файлы

Один раз выполни:

```bash
make deploy-env-init
```

После этого появятся файлы:

- `docker/env/app.deploy.env`
- `docker/env/db.deploy.env`

## 3. Заполнить настройки

### `docker/env/app.deploy.env`

Обязательно проверь и заполни:

- `DJANGO_SECRET_KEY`
- `MYCITYAIR_TOKEN`
- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`
- `DJANGO_ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`

Пример:

```env
DJANGO_SECRET_KEY=change-this-to-a-long-random-string
MYCITYAIR_TOKEN=your-token
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=change-this-password
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,air-monitor-web,123.123.123.123
CSRF_TRUSTED_ORIGINS=http://localhost,http://127.0.0.1,http://123.123.123.123
```

### `docker/env/db.deploy.env`

Тут достаточно проверить логин, пароль и имя базы. Если нет причин менять, можно оставить как есть.

## 4. Собрать и поднять проект

Если frontend лежит рядом с backend:

```bash
make deploy-build
make deploy-up-all FRONTEND_DIR=../air_monitor_front
```

Если пути другие, просто передай абсолютный путь до frontend:

```bash
make deploy-build
make deploy-up-all FRONTEND_DIR=/absolute/path/to/air_monitor_front
```

## 5. Проверить, что всё поднялось

После запуска должны открываться:

- `http://123.123.123.123/`
- `http://123.123.123.123/admin/`
- `http://123.123.123.123/api/docs`

Если admin не пускает, сначала проверь, что в `app.deploy.env` заполнены:

- `DJANGO_SUPERUSER_EMAIL`
- `DJANGO_SUPERUSER_PASSWORD`

При старте контейнера backend этот пользователь создаётся автоматически.


## Если что-то не взлетело

Сначала обычно хватает двух команд:

```bash
make deploy-logs
cd /path/to/air_monitor_front && make logs
```
