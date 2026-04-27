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

.PHONY: dev stop logs logs-agent logs-config logs-orchestrator logs-lark status clean db-shell

dev:
	docker compose up -d --build

stop:
	docker compose down

logs:
	docker compose logs -f

logs-agent:
	docker compose logs -f sre-agent

logs-config:
	docker compose logs -f config-service

logs-orchestrator:
	docker compose logs -f orchestrator

logs-lark:
	docker compose logs -f lark-bot

status:
	@docker compose --profile slack ps
	@echo ""
	@curl -sf http://localhost:8080/health > /dev/null 2>&1 && echo "config-service: healthy" || echo "config-service: down"
	@curl -sf http://localhost:8000/health > /dev/null 2>&1 && echo "sre-agent: healthy" || echo "sre-agent: down"
	@curl -sf http://localhost:8070/health > /dev/null 2>&1 && echo "orchestrator: healthy" || echo "orchestrator: down"

clean:
	docker compose --profile slack down -v --remove-orphans

db-shell:
	docker compose exec postgres psql -U incidentfox -d incidentfox
