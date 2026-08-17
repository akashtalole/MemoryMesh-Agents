FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

# Region/credentials are supplied at deploy time (AgentCore starter toolkit /
# deploy scripts set AWS_REGION from the deploy region). ANTHROPIC_API_KEY and
# COCKROACHDB_URL are injected as runtime environment variables by AgentCore,
# never baked into the image. COCKROACHDB_CLUSTER_ID (below) is the one
# exception: it's a build arg, not a secret, used only to fetch a public CA
# cert file at build time.
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

# Optional: this CockroachDB Cloud cluster's ID, forwarded by
# deploy-codebuild.sh/buildspec.yml from .env's COCKROACHDB_CLUSTER_ID.
# Bakes the cluster's CA cert into the image below so no runtime network
# fetch is needed — see src/memory/db.py for the runtime-fetch/system-trust
# fallbacks used when this build arg is left empty.
ARG COCKROACHDB_CLUSTER_ID=

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt
RUN uv pip install aws-opentelemetry-distro==0.18.0

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 bedrock_agentcore
ENV HOME=/home/bedrock_agentcore
USER bedrock_agentcore

# Same cert the CockroachDB Cloud console's own connect instructions have
# you fetch by hand — done here at build time instead so libpq's default
# sslmode=verify-full lookup path (~/.postgresql/root.crt) is already
# satisfied when the container starts. No-op if COCKROACHDB_CLUSTER_ID
# wasn't supplied.
RUN if [ -n "$COCKROACHDB_CLUSTER_ID" ]; then \
        curl --create-dirs -fsSL -o "$HOME/.postgresql/root.crt" \
            "https://cockroachlabs.cloud/clusters/${COCKROACHDB_CLUSTER_ID}/cert"; \
    fi

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "api"]
