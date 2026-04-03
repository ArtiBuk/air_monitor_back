.DEFAULT_GOAL := help

COMPOSE_PROJECT_NAME ?= air-monitor-back
COMPOSE := docker compose -p $(COMPOSE_PROJECT_NAME) -f docker/compose/infra.yml -f docker/compose/base.yml -f docker/compose/dev.yml -f docker/compose/volumes.yml
DEPLOY_COMPOSE := docker compose -p $(COMPOSE_PROJECT_NAME) -f docker/compose/infra.yml -f docker/compose/base.yml -f docker/compose/deploy.yml -f docker/compose/volumes.yml
PYTEST := DJANGO_ENV=test .venv/bin/pytest
RUFF := .venv/bin/ruff
AIR_MONITOR_NETWORK_NAME ?= air-monitor-network
APP_ENV_FILE ?= ../env/app.deploy.env
DB_ENV_FILE ?= ../env/db.deploy.env
FRONTEND_DIR ?= ../air_monitor_front
DEPLOY_STATE_DIR := .deploy
DEPLOY_FRONTEND_DIR_FILE := $(DEPLOY_STATE_DIR)/frontend_dir
WEB_CONTAINER_NAME ?= air-monitor-web

.PHONY: help up down stop start restart build rebuild ps logs shell-web migrate makemigrations create-superuser pytest pytest-create-db lint format check hooks-install network-create deploy-env-init deploy-up deploy-down deploy-stop deploy-start deploy-restart deploy-build deploy-rebuild deploy-ps deploy-logs deploy-shell-web deploy-create-superuser deploy-wait-web deploy-up-all deploy-down-all

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
	@printf "  make create-superuser Создать superuser в dev-контуре\n"
	@printf "  make pytest           Запустить pytest с переиспользованием тестовой БД\n"
	@printf "  make pytest-create-db Пересоздать тестовую БД pytest\n"
	@printf "  make lint             Запустить ruff check\n"
	@printf "  make format           Запустить ruff format и ruff check --fix\n"
	@printf "  make check            Запустить lint и тесты\n"
	@printf "  make hooks-install    Подключить локальные git hooks из .githooks\n"
	@printf "\nКоманды для деплоя:\n"
	@printf "  make deploy-up        Поднять production-контур backend\n"
	@printf "  make deploy-down      Остановить и удалить production-контур backend\n"
	@printf "  make deploy-logs      Смотреть логи production-контейнеров\n"
	@printf "  make deploy-shell-web Открыть shell внутри production web-контейнера\n"
	@printf "  make deploy-create-superuser Создать superuser в production-контуре\n"
	@printf "  make deploy-up-all    Поднять backend и frontend одной командой\n"
	@printf "  make deploy-down-all  Остановить backend и frontend одной командой\n"

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

create-superuser:
	$(COMPOSE) exec web python manage.py createsuperuser

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

network-create:
	@docker network inspect $(AIR_MONITOR_NETWORK_NAME) >/dev/null 2>&1 || docker network create $(AIR_MONITOR_NETWORK_NAME)

deploy-env-init:
	@test -f docker/env/app.deploy.env || cp docker/env/app.deploy.example.env docker/env/app.deploy.env
	@test -f docker/env/db.deploy.env || cp docker/env/db.deploy.example.env docker/env/db.deploy.env

deploy-up: network-create deploy-env-init
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) up -d

deploy-down:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) down

deploy-stop:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) stop

deploy-start: network-create deploy-env-init
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) start

deploy-restart:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) restart $(SERVICE)

deploy-build: network-create deploy-env-init
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) build

deploy-rebuild: network-create deploy-env-init
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) build --no-cache

deploy-ps:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) ps

deploy-logs:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) logs -f --tail=200 $(SERVICE)

deploy-shell-web:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) exec web /bin/sh

deploy-create-superuser:
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) exec web python manage.py createsuperuser

deploy-wait-web:
	@attempt=0; \
	while true; do \
		status="$$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $(WEB_CONTAINER_NAME) 2>/dev/null || true)"; \
		if [ "$$status" = "healthy" ]; then \
			break; \
		fi; \
		attempt=$$((attempt + 1)); \
		if [ $$attempt -ge 60 ]; then \
			printf "Timed out waiting for %s to become healthy\n" "$(WEB_CONTAINER_NAME)" >&2; \
			docker logs $(WEB_CONTAINER_NAME) --tail=200 >&2 || true; \
			exit 1; \
		fi; \
		sleep 2; \
	done

deploy-up-all: deploy-up deploy-wait-web
	@test -d "$(FRONTEND_DIR)" || (printf "FRONTEND_DIR not found: %s\n" "$(FRONTEND_DIR)" >&2; exit 1)
	@mkdir -p "$(DEPLOY_STATE_DIR)"
	@printf "%s\n" "$$(cd "$(FRONTEND_DIR)" && pwd)" > "$(DEPLOY_FRONTEND_DIR_FILE)"
	$(MAKE) -C $(FRONTEND_DIR) up AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME)

deploy-down-all:
	@frontend_dir="$(FRONTEND_DIR)"; \
	if test -f "$(DEPLOY_FRONTEND_DIR_FILE)"; then frontend_dir="$$(cat "$(DEPLOY_FRONTEND_DIR_FILE)")"; fi; \
	if test -d "$$frontend_dir"; then \
		$(MAKE) -C "$$frontend_dir" down AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME); \
	else \
		docker rm -f air-monitor-frontend >/dev/null 2>&1 || true; \
	fi
	@rm -f "$(DEPLOY_FRONTEND_DIR_FILE)"
	AIR_MONITOR_NETWORK_NAME=$(AIR_MONITOR_NETWORK_NAME) APP_ENV_FILE=$(APP_ENV_FILE) DB_ENV_FILE=$(DB_ENV_FILE) $(DEPLOY_COMPOSE) down
