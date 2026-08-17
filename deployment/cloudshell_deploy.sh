#!/bin/bash
set -euo pipefail

# One-shot deploy for AWS CloudShell: installs Python deps, makes sure this
# AWS account/region has a GitHub source credential for CodeBuild (needed
# once — deploy-codebuild.sh's CodeBuild project clones straight from
# GitHub), fills in a .env interactively if you don't already have one, then
# runs deploy-codebuild.sh end to end (CodeBuild build -> AgentCore deploy).
# deploy-runtime.py forwards ANTHROPIC_API_KEY/COCKROACHDB_URL/etc. from
# that .env onto the runtime automatically, so there's no separate console
# trip after this finishes.
#
# Run from the repo root, after cloning:
#   bash deployment/cloudshell_deploy.sh
#
# NOTE: this stands up the AgentCore *runtime* only — the piece that runs
# the LangGraph workflow. It's invoked with SigV4-signed requests, not a
# browsable URL. To actually give judges something to click, you still need
# to run the FastAPI + React app (server/) somewhere public — see the
# "What this doesn't do" note this script prints at the end.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="${PROJECT_DIR}/config"
BASE_SETTINGS="${CONFIG_DIR}/static-config.yaml"
cd "$PROJECT_DIR"

if command -v yq >/dev/null 2>&1; then
    REGION=$(yq eval '.aws.region' "${BASE_SETTINGS}")
else
    REGION=$(grep "region:" "${BASE_SETTINGS}" | head -1 | sed 's/.*region: *\([^ #]*\).*/\1/')
fi

echo "📦 Installing Python dependencies..."
pip install -q -r requirements.txt

# === .env: fill in interactively if missing ===
if [ ! -f .env ]; then
    echo ""
    echo "📝 No .env found — let's create one with just what's needed to deploy."
    cp .env.example .env

    read -rsp "Anthropic API key (sk-ant-...): " ANTHROPIC_API_KEY_INPUT
    echo ""
    read -rsp "CockroachDB connection string: " COCKROACHDB_URL_INPUT
    echo ""
    read -rsp "Judge access password (blank = app stays open to anyone with the URL): " JUDGE_PW_INPUT
    echo ""

    python3 - "$ANTHROPIC_API_KEY_INPUT" "$COCKROACHDB_URL_INPUT" "$JUDGE_PW_INPUT" <<'PYEOF'
import re
import sys
import pathlib

api_key, db_url, judge_pw = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(".env")
text = p.read_text()


def set_var(text: str, key: str, value: str) -> str:
    return re.sub(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.MULTILINE)


text = set_var(text, "ANTHROPIC_API_KEY", api_key)
text = set_var(text, "COCKROACHDB_URL", db_url)
if judge_pw:
    text = set_var(text, "JUDGE_ACCESS_PASSWORD", judge_pw)
p.write_text(text)
PYEOF
    echo "   ✅ .env written."
else
    echo "✅ Using existing .env"
fi

# === GitHub source credentials (one-time, needed for CodeBuild's GITHUB source) ===
if ! aws codebuild list-source-credentials --region "$REGION" \
    --query 'sourceCredentialsInfos[?serverType==`GITHUB`]' --output text | grep -q .; then
    echo ""
    echo "🔑 CodeBuild has no GitHub source credential registered in ${REGION} yet —"
    echo "   required once so it's allowed to clone from GitHub. Create a token at"
    echo "   https://github.com/settings/tokens (classic, 'public_repo' scope is enough"
    echo "   for a public repo)."
    read -rsp "   Paste your GitHub personal access token: " GITHUB_PAT
    echo ""
    aws codebuild import-source-credentials --region "$REGION" \
        --server-type GITHUB --auth-type PERSONAL_ACCESS_TOKEN --token "$GITHUB_PAT" >/dev/null
    echo "   ✅ GitHub source credential registered."
else
    echo "✅ GitHub source credential already registered in ${REGION}."
fi

# === Build on CodeBuild + deploy to AgentCore (also forwards .env onto the runtime) ===
echo ""
bash "${SCRIPT_DIR}/deploy-codebuild.sh"

echo ""
echo "================================================================"
echo "⚠️  What this script does NOT do: AgentCore Runtime isn't a"
echo "   browsable URL — it's invoked via SigV4-signed requests, never"
echo "   directly from a browser. To give judges something to click,"
echo "   you still need to run the FastAPI + React app (server/)"
echo "   somewhere public, pointed at this runtime ARN (already written"
echo "   to config/dynamic-config.yaml). Fastest options from here:"
echo "     - AWS App Runner, pointed at this same repo/Dockerfile"
echo "     - Any small always-on host: make web-build && uvicorn"
echo "       server.main:app --host 0.0.0.0 --port 8000"
echo "   Or skip hosting it publicly entirely — 'make dev' locally"
echo "   already proxies to this deployed runtime once"
echo "   config/dynamic-config.yaml has the ARN, which is enough for a"
echo "   local judged demo or a screen-recorded video."
echo "================================================================"
