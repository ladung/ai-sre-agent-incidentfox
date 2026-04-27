# IncidentFox — Local Development
#
# Usage:
#   make dev        Start all services (postgres, config-service, credential-proxy,
#                   orchestrator, sre-agent, slack-bot, lark-bot)
#                   Note: slack-bot requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN in .env
#                   Note: lark-bot requires LARK_APP_ID + LARK_APP_SECRET + LARK_TENANT_KEY
#   make stop       Stop all services
#   make logs       Follow all logs
#   make clean      Remove containers, volumes, and images
#   make db-shell   Open psql shell
#
# Compose tool detection:
#   Auto-detects `docker compose` v2 (preferred) and falls back to v1
#   `docker-compose`. With v1, BuildKit is disabled so its image-config
#   parser doesn't crash on BuildKit OCI metadata (KeyError: 'ContainerConfig').

DC := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
COMPOSE_FILE ?= docker-compose.yml

ifeq ($(DC),docker-compose)
export DOCKER_BUILDKIT = 0
export COMPOSE_DOCKER_CLI_BUILD = 0
endif

.PHONY: dev stop logs logs-agent logs-config logs-orchestrator logs-lark status clean db-shell which-compose

which-compose:
	@echo "Using compose: $(DC)"
	@echo "Compose file:  $(COMPOSE_FILE)"
ifeq ($(DC),docker-compose)
	@echo "BuildKit:      disabled (v1 compatibility)"
else
	@echo "BuildKit:      enabled"
endif

dev:
	$(DC) -f $(COMPOSE_FILE) up -d --build

stop:
	$(DC) -f $(COMPOSE_FILE) down

logs:
	$(DC) -f $(COMPOSE_FILE) logs -f

logs-agent:
	$(DC) -f $(COMPOSE_FILE) logs -f sre-agent

logs-config:
	$(DC) -f $(COMPOSE_FILE) logs -f config-service

logs-orchestrator:
	$(DC) -f $(COMPOSE_FILE) logs -f orchestrator

logs-lark:
	$(DC) -f $(COMPOSE_FILE) logs -f lark-bot

status:
	@$(DC) -f $(COMPOSE_FILE) ps
	@echo ""
	@curl -sf http://localhost:8080/health > /dev/null 2>&1 && echo "config-service: healthy" || echo "config-service: down"
	@curl -sf http://localhost:8000/health > /dev/null 2>&1 && echo "sre-agent: healthy" || echo "sre-agent: down"
	@curl -sf http://localhost:8070/health > /dev/null 2>&1 && echo "orchestrator: healthy" || echo "orchestrator: down"

clean:
	$(DC) -f $(COMPOSE_FILE) down -v --remove-orphans

db-shell:
	$(DC) -f $(COMPOSE_FILE) exec postgres psql -U incidentfox -d incidentfox
