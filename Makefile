# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Licensed under Apache-2.0; see LICENSE. No warranties.
SHELL := /bin/bash
COMPOSE := docker compose
PROFILE ?=
BACKUP_DIR ?=
CONFIRM_PROJECT ?=
.PHONY: help configure build up up-all demo integrations down health test headers smoke intelligence backup restore

help:
	@printf '%s\n' \
		'make configure                 Generate ignored local secrets and infrastructure configuration' \
		'make up [PROFILE=...]          Build core and an optional profile; wait for readiness' \
		'make up-all                    Build/start all profiles, including local observability' \
		'make demo                      Full local stack, model download and n8n workflow initialization' \
		'make integrations              Initialize optional services after make up-all' \
		'make down                      Stop this project, retaining persistent volumes' \
		'make test / headers            Regression tests / per-file licensing checks' \
		'make smoke                     Real SSO, evidence, amendment, rejection and export journey' \
		'make intelligence              Real MCP and Ollama smoke after make smoke and model download' \
		'make backup [BACKUP_DIR=x]      Private cold backup; briefly stops writers' \
		'make restore BACKUP_DIR=x CONFIRM_PROJECT=bidweave   Replace only the confirmed project state'

configure:
	@python3 scripts/configure.py

build: configure
	$(COMPOSE) $(if $(PROFILE),--profile "$(PROFILE)",) build

up: configure
	$(COMPOSE) $(if $(PROFILE),--profile "$(PROFILE)",) up -d --build --wait --wait-timeout 300

up-all: configure
	OTEL_ENABLED=true $(COMPOSE) --profile '*' up -d --build --wait --wait-timeout 300

demo: up-all
	$(MAKE) integrations

integrations:
	python3 scripts/integrations.py

down:
	$(COMPOSE) --profile '*' down

health:
	$(COMPOSE) --profile '*' ps
	@curl --fail --silent --show-error http://localhost:8090/api/health
	@printf '\n'

test:
	uv run --project services/api --extra dev --exact --frozen pytest services/api/tests
	python3 -m unittest discover -s scripts -p 'test_*.py'

headers:
	python3 scripts/check-headers.py
	uvx --from reuse==5.0.2 reuse lint

smoke:
	uv run --project services/api python scripts/smoke.py

intelligence:
	uv run --project services/api python scripts/llm-smoke.py

backup:
	python3 scripts/backup.py create $(if $(BACKUP_DIR),--directory "$(BACKUP_DIR)",)

restore:
	@test -n "$(BACKUP_DIR)" -a -n "$(CONFIRM_PROJECT)" || (printf 'BACKUP_DIR and CONFIRM_PROJECT are required\n' >&2; exit 2)
	python3 scripts/backup.py restore --directory "$(BACKUP_DIR)" --confirm-project "$(CONFIRM_PROJECT)"
