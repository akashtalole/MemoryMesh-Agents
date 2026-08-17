FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

# Region/credentials are supplied at deploy time (AgentCore starter toolkit /
# deploy scripts set AWS_REGION from the deploy region). ANTHROPIC_API_KEY and
# COCKROACHDB_URL are injected as runtime environment variables by AgentCore,
# never baked into the image.
ENV UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_PROGRESS=1 \
    PYTHONUNBUFFERED=1 \
    DOCKER_CONTAINER=1

COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt
RUN uv pip install aws-opentelemetry-distro==0.18.0
# Download CockroachDB CA certificate
RUN mkdir -p /app/certs && curl --fail --silent --show-error --create-dirs -o /app/certs/root.crt 'https://cockroachlabs.cloud/clusters/2a8a467b-46cd-49e2-b3bc-4c92678b0385/cert'
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore

EXPOSE 9000
EXPOSE 8000
EXPOSE 8080

COPY . .

CMD ["opentelemetry-instrument", "python", "-m", "api"]
