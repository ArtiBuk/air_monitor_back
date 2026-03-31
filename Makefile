.DEFAULT_GOAL := help

COMPOSE := docker compose -f docker/compose/infra.yml -f docker/compose/base.yml -f docker/compose/volumes.yml
PYTEST := DJANGO_ENV=test .venv/bin/pytest
RUFF := .venv/bin/ruff

.PHONY: help up down stop start restart build rebuild ps logs shell-web migrate makemigrations pytest pytest-create-db lint format check hooks-install

help:
	@printf "Доступные команды:\n"
	@printf "  make up               Поднять стек в фоне без принудительной пересборки\n"
	@printf "  make down             Остановить и удалить контейнеры\n"
	@printf "  make stop             Остановить контейнеры без удаления\n"
	@printf "  make start            Запустить ранее созданные контейнеры\n"
	@printf "  make restart          Перезапустить работающие контейнеры без пересборки\n"
	@printf "  make build            Собрать образы при изменении Dockerfile или зависимостей\n"
	@printf "  make rebuild          Полностью пересобрать образы без кэша\n"
	@printf "  make ps               Показать состояние контейнеров\n"
	@printf "  make logs             Смотреть логи всех сервисов\n"
	@printf "  make logs SERVICE=web Смотреть логи конкретного сервиса\n"
	@printf "  make shell-web        Открыть shell внутри web-контейнера\n"
	@printf "  make migrate          Выполнить Django migrations внутри web-контейнера\n"
	@printf "  make makemigrations   Создать Django migrations внутри web-контейнера\n"
	@printf "  make pytest           Запустить pytest с переиспользованием тестовой БД\n"
	@printf "  make pytest-create-db Пересоздать тестовую БД pytest\n"
	@printf "  make lint             Запустить ruff check\n"
	@printf "  make format           Запустить ruff format и ruff check --fix\n"
	@printf "  make check            Запустить lint и тесты\n"
	@printf "  make hooks-install    Подключить локальные git hooks из .githooks\n"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

stop:
	$(COMPOSE) stop

start:
	$(COMPOSE) start

restart:
	$(COMPOSE) restart $(SERVICE)

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200 $(SERVICE)

shell-web:
	$(COMPOSE) exec web /bin/sh

migrate:
	$(COMPOSE) exec web python manage.py migrate

makemigrations:
	$(COMPOSE) exec web python manage.py makemigrations

pytest:
	$(PYTEST)

pytest-create-db:
	$(PYTEST) --create-db

lint:
	$(RUFF) check .

format:
	$(RUFF) check --fix .
	$(RUFF) format .

check: lint pytest

hooks-install:
	git config core.hooksPath .githooks
