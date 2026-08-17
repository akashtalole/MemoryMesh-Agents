.PHONY: help deploy deploy-codebuild deploy-cloudshell destroy start-client prerequisites clean logs status init-memory seed-memory provision-cluster web-install web-dev web-build api-dev dev

help:
	@echo "MemoryMesh Agent — CockroachDB memory for LangGraph agents on AWS AgentCore"
	@echo "============================================================================"
	@echo ""
	@echo "Modern UI (React + FastAPI):"
	@echo "  make dev               - Run the FastAPI backend AND the Vite dev server together"
	@echo "  make api-dev           - Run only the FastAPI backend (with reload) on :8000"
	@echo "  make web-dev           - Run only the Vite dev server on :5173 (proxies /api to :8000)"
	@echo "  make web-install       - npm install the frontend"
	@echo "  make web-build         - Build the frontend into web/dist (served by FastAPI in prod)"
	@echo ""
	@echo "Memory / CockroachDB:"
	@echo "  make provision-cluster - Create a free CockroachDB Cloud cluster via ccloud CLI"
	@echo "  make init-memory       - Create/migrate CockroachDB memory tables + vector index"
	@echo "  make seed-memory       - Seed a few historical cases into long-term case memory"
	@echo ""
	@echo "AWS AgentCore deployment:"
	@echo "  make deploy            - Full AgentCore deployment (IAM + ECR + local Docker build + runtime)"
	@echo "  make deploy-codebuild  - Same, but builds the ARM64 image on AWS CodeBuild (no local Docker)"
	@echo "  make deploy-cloudshell - One-shot: prompts for .env, then runs deploy-codebuild end to end"
	@echo "  make prerequisites     - Set up IAM role and ECR only"
	@echo "  make destroy           - Delete all AgentCore resources"
	@echo "  make logs              - Tail AgentCore runtime logs"
	@echo "  make status            - Check deployment status"
	@echo ""
	@echo "Other:"
	@echo "  make start-client      - Start the legacy Streamlit UI (ops quick-look)"
	@echo "  make clean             - Clean up temporary files"

web-install:
	@echo "📦 Installing frontend dependencies..."
	@cd web && npm install

web-dev: web-install
	@echo "🎨 Starting Vite dev server on http://localhost:5173 (proxies /api -> :8000)..."
	@cd web && npm run dev

web-build: web-install
	@echo "🏗️  Building frontend into web/dist..."
	@cd web && npm run build

api-dev:
	@echo "⚙️  Starting FastAPI backend on http://localhost:8000..."
	@uvicorn server.main:app --reload --port 8000

dev:
	@echo "🚀 Starting FastAPI (:8000) + Vite dev server (:5173)..."
	@echo "   Open http://localhost:5173 — Ctrl-C stops both."
	@trap 'kill 0' EXIT INT TERM; \
	uvicorn server.main:app --reload --port 8000 & \
	(cd web && npm install --silent && npm run dev) & \
	wait

provision-cluster:
	@echo "🐘 Provisioning a CockroachDB Cloud cluster via ccloud CLI..."
	@./scripts/provision_cluster.sh

init-memory:
	@echo "🧠 Initializing CockroachDB memory schema (checkpoints, chat history, case memory)..."
	@python scripts/init_memory_schema.py

seed-memory:
	@echo "🌱 Seeding CockroachDB case memory with sample past investigations..."
	@python scripts/seed_case_memory.py

deploy:
	@echo "🚀 Running full deployment..."
	@cd deployment && ./deploy.sh

deploy-codebuild:
	@echo "🚀 Running full deployment via AWS CodeBuild (no local Docker)..."
	@cd deployment && ./deploy-codebuild.sh

deploy-cloudshell:
	@echo "🚀 Running one-shot deployment for AWS CloudShell..."
	@bash deployment/cloudshell_deploy.sh

prerequisites:
	@echo "🔐 Setting up prerequisites only..."
	@cd deployment && ./prerequisites.sh

destroy:
	@echo "🗑️  Destroying AgentCore deployment..."
	@cd deployment && ./delete.sh

start-client:
	@echo "🎨 Starting Streamlit UI..."
	@streamlit run app.py

logs:
	@echo "📊 Finding and tailing AgentCore runtime logs..."
	@LOG_GROUP=$$(aws logs describe-log-groups \
		--log-group-name-prefix "/aws/bedrock-agentcore/runtimes/memorymesh_agent_workflow" \
		--region us-east-1 \
		--query 'logGroups[0].logGroupName' \
		--output text 2>/dev/null) && \
	if [ -z "$$LOG_GROUP" ] || [ "$$LOG_GROUP" = "None" ]; then \
		echo "❌ No log group found. Has the runtime been invoked yet?"; \
	else \
		echo "   Log group: $$LOG_GROUP"; \
		aws logs tail "$$LOG_GROUP" --follow --region us-east-1; \
	fi

status:
	@echo "📋 Checking deployment status..."
	@echo ""
	@echo "Configuration:"
	@cat config/dynamic-config.yaml
	@echo ""
	@echo "AgentCore Runtimes:"
	@aws bedrock-agentcore-control list-agent-runtimes --region us-east-1 --query 'agentRuntimes[?agentRuntimeName==`memorymesh_agent_workflow`]' --output table

clean:
	@echo "🧹 Cleaning temporary files..."
	@rm -f deployment/trust-policy-final.json
	@rm -f deployment/permissions-policy-final.json
	@echo "✅ Cleanup complete"
