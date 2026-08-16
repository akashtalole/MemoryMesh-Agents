import os

from dotenv import load_dotenv

load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "").lower()

# Logging Configuration
LOGGING_CONFIG = {
    "level": os.getenv("LOG_LEVEL", "INFO").upper(),
    "format": os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
    "to_console": os.getenv("LOG_TO_CONSOLE", "false").lower() in ("true", "1", "yes"),
    "to_file": os.getenv("LOG_TO_FILE", "true").lower() in ("true", "1", "yes"),
    "directory": os.getenv("LOG_DIRECTORY", "logs"),
}

# Only used for hosting (Amazon Bedrock AgentCore) — not for model inference,
# which goes straight to the Anthropic API.
AWS_CONFIG = {
    "region_name": os.getenv("AWS_REGION", "us-east-1"),
}

ANTHROPIC_CONFIG = {
    "api_key": os.getenv("ANTHROPIC_API_KEY"),
    "model_id": os.getenv("ANTHROPIC_MODEL_ID", "claude-sonnet-4-6"),
}

COCKROACHDB_CONFIG = {
    "url": os.getenv("COCKROACHDB_URL"),
    "chat_history_table": os.getenv("COCKROACHDB_CHAT_HISTORY_TABLE", "message_store"),
    "case_memory_table": os.getenv("COCKROACHDB_CASE_MEMORY_TABLE", "case_memory"),
    "mcp_url": os.getenv("COCKROACHDB_MCP_URL", "https://cockroachlabs.cloud/mcp"),
}
