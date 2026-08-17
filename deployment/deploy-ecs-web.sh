#!/bin/bash
set -euo pipefail

# Build the public-facing web app (server/ + web/) via CodeBuild and deploy
# it to Amazon ECS Express Mode — one command provisions a Fargate service,
# an internet-facing Application Load Balancer with automatic HTTPS, and
# autoscaling, giving you a public https://<name>.ecs.<region>.on.aws/ URL.
#
# This is separate from the AgentCore deployment (make deploy /
# deploy-codebuild) — that one runs the LangGraph workflow; this one runs
# the FastAPI + React app judges actually click on, configured to proxy
# chat requests to that already-deployed runtime (AGENT_BACKEND_MODE=agentcore).
#
# We use ECS Express Mode rather than AWS App Runner because App Runner is
# closed to new customers as of this writing — Express Mode is AWS's own
# recommended replacement, with the same one-command simplicity.
#
# Prerequisites:
#   - The AgentCore runtime must already be deployed (make deploy or
#     make deploy-codebuild) — this script reads its ARN from
#     config/dynamic-config.yaml.
#   - A .env with at least COCKROACHDB_URL set. ANTHROPIC_API_KEY is NOT
#     needed here — this service only proxies to AgentCore, it never runs
#     the workflow itself.
#   - Source is pulled straight from GitHub, same as deploy-codebuild.sh —
#     push your changes first. Requires the same one-time CodeBuild GitHub
#     source credential (see deploy-codebuild.sh's header comment).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="${PROJECT_DIR}/config"
BASE_SETTINGS="${CONFIG_DIR}/static-config.yaml"
DYNAMIC_CONFIG="${CONFIG_DIR}/dynamic-config.yaml"
cd "$PROJECT_DIR"

GITHUB_REPO_URL="${GITHUB_REPO_URL:-https://github.com/akashtalole/MemoryMesh-Agents.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

read_yaml() {
    python3 -c "
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f) or {}
for key in sys.argv[2].split('.'):
    data = (data or {}).get(key) if isinstance(data, dict) else None
print(data if data is not None else '')
" "$1" "$2"
}

# Reads a single key out of .env via python-dotenv's own parser — NOT bash
# `source`, which executes .env as a shell script and silently mangles any
# value containing $, `, ", #, spaces, or other shell-special characters
# (a real problem for a password value).
read_dotenv_var() {
    python3 -c "
import sys
from dotenv import dotenv_values
print(dotenv_values(sys.argv[1]).get(sys.argv[2]) or '')
" "$1" "$2" 2>/dev/null || true
}

REGION=$(read_yaml "$BASE_SETTINGS" "aws.region")
ECR_REPO=$(read_yaml "$BASE_SETTINGS" "web.ecr_repo")
SERVICE_NAME=$(read_yaml "$BASE_SETTINGS" "web.service_name")
PORT=$(read_yaml "$BASE_SETTINGS" "web.port")
PORT="${PORT:-8000}"

if [ ! -f "$DYNAMIC_CONFIG" ]; then
    echo "❌ ${DYNAMIC_CONFIG} not found — deploy the AgentCore runtime first"
    echo "   (make deploy or make deploy-codebuild), then re-run this script."
    exit 1
fi
RUNTIME_ARN=$(read_yaml "$DYNAMIC_CONFIG" "runtime.arn")
if [ -z "$RUNTIME_ARN" ]; then
    echo "❌ No runtime ARN found in ${DYNAMIC_CONFIG} — deploy the AgentCore"
    echo "   runtime first (make deploy or make deploy-codebuild)."
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT_ID" ]; then
    echo "❌ Failed to get AWS Account ID. Please ensure AWS credentials are configured."
    exit 1
fi

CODEBUILD_PROJECT="${ECR_REPO}-build"
CODEBUILD_ROLE_NAME="memorymesh-agentcore-web-codebuild-role"
EXEC_ROLE_NAME="ecsTaskExecutionRole"
INFRA_ROLE_NAME="ecsInfrastructureRoleForExpressServices"
TASK_ROLE_NAME="memorymesh-agent-web-task-role"

echo "📝 Configuration:"
echo "   Region: ${REGION}"
echo "   ECR Repository: ${ECR_REPO}"
echo "   CodeBuild Project: ${CODEBUILD_PROJECT}"
echo "   ECS Express service: ${SERVICE_NAME}"
echo "   Container port: ${PORT}"
echo "   AgentCore runtime ARN: ${RUNTIME_ARN}"

# Load .env for COCKROACHDB_URL / JUDGE_ACCESS_PASSWORD / etc, via Python's
# dotenv parser rather than bash `source` — sourcing .env as a shell script
# silently mangles any value containing $, `, ", #, spaces, or other
# shell-special characters (a real problem for a password). Real shell env
# vars, if you're setting these that way instead, take priority.
if [ -f .env ]; then
    : "${COCKROACHDB_URL:=$(read_dotenv_var .env COCKROACHDB_URL)}"
    : "${COCKROACHDB_CLUSTER_ID:=$(read_dotenv_var .env COCKROACHDB_CLUSTER_ID)}"
    : "${JUDGE_ACCESS_PASSWORD:=$(read_dotenv_var .env JUDGE_ACCESS_PASSWORD)}"
    : "${JUDGE_SESSION_TTL_HOURS:=$(read_dotenv_var .env JUDGE_SESSION_TTL_HOURS)}"
    : "${COOKIE_SECURE:=$(read_dotenv_var .env COOKIE_SECURE)}"
fi
if [ -z "${COCKROACHDB_URL:-}" ]; then
    echo "❌ COCKROACHDB_URL not set (checked .env and the shell) — the memory"
    echo "   panel needs it. Set it and re-run."
    exit 1
fi

# === ECR repo for the web image ===
echo ""
echo "📦 Ensuring ECR repository..."
if ! aws ecr describe-repositories --repository-names "${ECR_REPO}" --region "${REGION}" >/dev/null 2>&1; then
    aws ecr create-repository --repository-name "${ECR_REPO}" --region "${REGION}" >/dev/null
    echo "   ✅ ECR repository created: ${ECR_REPO}"
else
    echo "   ✅ ECR repository exists: ${ECR_REPO}"
fi

# === CodeBuild service role ===
echo ""
echo "🔐 Ensuring CodeBuild service role..."
CB_ROLE_EXISTS=$(aws iam get-role --role-name "${CODEBUILD_ROLE_NAME}" 2>&1 || true)
if echo "$CB_ROLE_EXISTS" | grep -q "NoSuchEntity"; then
    CB_TRUST_FILE="$(mktemp)"
    cat > "$CB_TRUST_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "codebuild.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF
    CB_ROLE_ARN=$(aws iam create-role \
        --role-name "${CODEBUILD_ROLE_NAME}" \
        --assume-role-policy-document "file://${CB_TRUST_FILE}" \
        --description "CodeBuild role for building MemoryMesh Agent's web app image" \
        --query 'Role.Arn' --output text)
    rm -f "$CB_TRUST_FILE"
    echo "   ✅ Role created: ${CB_ROLE_ARN}"
    echo "   ⏳ Waiting for role to propagate (20 seconds)..."
    sleep 20
else
    CB_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${CODEBUILD_ROLE_NAME}"
    echo "   ✅ Role exists: ${CB_ROLE_ARN}"
fi

CB_PERMISSIONS_FILE="$(mktemp)"
cat > "$CB_PERMISSIONS_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/codebuild/${CODEBUILD_PROJECT}*"
    },
    { "Effect": "Allow", "Action": ["ecr:GetAuthorizationToken"], "Resource": "*" },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "arn:aws:ecr:${REGION}:${ACCOUNT_ID}:repository/${ECR_REPO}"
    }
  ]
}
EOF
aws iam put-role-policy \
    --role-name "${CODEBUILD_ROLE_NAME}" \
    --policy-name "${CODEBUILD_ROLE_NAME}-permissions" \
    --policy-document "file://${CB_PERMISSIONS_FILE}"
rm -f "$CB_PERMISSIONS_FILE"
echo "   ✅ Permissions policy attached"

# === CodeBuild project (source = GitHub, native x86_64 compute) ===
echo ""
echo "🏗️  Ensuring CodeBuild project..."
PROJECT_DEF_FILE="$(mktemp)"
cat > "$PROJECT_DEF_FILE" <<EOF
{
  "name": "${CODEBUILD_PROJECT}",
  "source": {
    "type": "GITHUB",
    "location": "${GITHUB_REPO_URL}",
    "buildspec": "deployment/buildspec-web.yml",
    "gitCloneDepth": 1
  },
  "sourceVersion": "${GITHUB_BRANCH}",
  "artifacts": { "type": "NO_ARTIFACTS" },
  "environment": {
    "type": "LINUX_CONTAINER",
    "image": "aws/codebuild/standard:7.0",
    "computeType": "BUILD_GENERAL1_SMALL",
    "privilegedMode": true,
    "environmentVariables": [
      { "name": "AWS_ACCOUNT_ID", "value": "${ACCOUNT_ID}" },
      { "name": "IMAGE_REPO_NAME", "value": "${ECR_REPO}" },
      { "name": "AWS_DEFAULT_REGION", "value": "${REGION}" }
    ]
  },
  "serviceRole": "${CB_ROLE_ARN}"
}
EOF

if aws codebuild batch-get-projects --names "${CODEBUILD_PROJECT}" --region "${REGION}" \
    --query 'projects[0].name' --output text 2>/dev/null | grep -qx "${CODEBUILD_PROJECT}"; then
    echo "   Updating existing project..."
    aws codebuild update-project --region "${REGION}" --cli-input-json "file://${PROJECT_DEF_FILE}" >/dev/null
    echo "   ✅ Project updated: ${CODEBUILD_PROJECT}"
else
    echo "   Creating project..."
    if ! aws codebuild create-project --region "${REGION}" --cli-input-json "file://${PROJECT_DEF_FILE}" >/dev/null 2>/tmp/codebuild-web-create-err; then
        if grep -qi "source credentials\|OAuth\|source provider" /tmp/codebuild-web-create-err 2>/dev/null; then
            echo "   ❌ CodeBuild has no GitHub source credential registered for this account/region yet."
            echo "      One-time fix (same as deploy-codebuild.sh needs) — either connect via the"
            echo "      console (CodeBuild -> Settings -> Source providers -> Connect to GitHub), or run:"
            echo "        aws codebuild import-source-credentials --server-type GITHUB \\"
            echo "          --auth-type PERSONAL_ACCESS_TOKEN --token <your-github-PAT>"
            echo "      Then re-run this script."
        fi
        cat /tmp/codebuild-web-create-err >&2
        rm -f /tmp/codebuild-web-create-err
        rm -f "$PROJECT_DEF_FILE"
        exit 1
    fi
    rm -f /tmp/codebuild-web-create-err
    echo "   ✅ Project created: ${CODEBUILD_PROJECT}"
fi
rm -f "$PROJECT_DEF_FILE"

# === BUILD ===
# A freshly-created CodeBuild service role's inline policy can take a little
# while to propagate — CodeBuild sometimes tries (and fails) to assume it
# before IAM has caught up, failing in the QUEUED phase with an
# "does not allow AWS CodeBuild to create... CloudWatch Logs" access-denied
# error. Retry a couple of times before treating it as a real failure.
echo ""
echo "🔨 Building the web app image (native x86_64 — no local Docker involved)..."

MAX_ATTEMPTS=3
ATTEMPT=1
STATUS=""
BUILD_ID=""
while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
    BUILD_ID=$(aws codebuild start-build --project-name "${CODEBUILD_PROJECT}" --region "${REGION}" \
        --source-version "${GITHUB_BRANCH}" --query 'build.id' --output text)
    echo "   Build ID: ${BUILD_ID} (attempt ${ATTEMPT}/${MAX_ATTEMPTS})"

    STATUS="IN_PROGRESS"
    while [ "$STATUS" = "IN_PROGRESS" ]; do
        sleep 10
        STATUS=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${REGION}" \
            --query 'builds[0].buildStatus' --output text)
        echo "   Status: ${STATUS}"
    done

    if [ "$STATUS" = "SUCCEEDED" ]; then
        break
    fi

    FAIL_MSG=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${REGION}" \
        --query 'builds[0].phases[?phaseStatus!=`SUCCEEDED` && phaseStatus!=`IN_PROGRESS`] | [0].contexts[0].message' \
        --output text 2>/dev/null || true)
    if [ "$ATTEMPT" -lt "$MAX_ATTEMPTS" ] && echo "$FAIL_MSG" | grep -qi "does not allow AWS CodeBuild\|not authorized\|AccessDenied"; then
        echo "   ⚠️  Looks like an IAM propagation delay: ${FAIL_MSG}"
        echo "   ⏳ Waiting 20s and retrying..."
        sleep 20
    else
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
done

if [ "$STATUS" != "SUCCEEDED" ]; then
    echo ""
    echo "❌ CodeBuild build ${STATUS}"
    LOG_GROUP=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${REGION}" \
        --query 'builds[0].logs.groupName' --output text)
    LOG_STREAM=$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${REGION}" \
        --query 'builds[0].logs.streamName' --output text)
    echo "   View logs:"
    echo "   aws logs get-log-events --region ${REGION} --log-group-name ${LOG_GROUP} --log-stream-name ${LOG_STREAM}"
    echo "   Or see exactly which phase failed and why:"
    echo "   aws codebuild batch-get-builds --ids ${BUILD_ID} --region ${REGION} --query 'builds[0].phases'"
    exit 1
fi
echo "   ✅ Build succeeded — image pushed to ECR"

IMAGE_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}:latest"

# === IAM roles for ECS Express Mode ===
NEW_ROLE_CREATED=0

ensure_role() {
    local role_name="$1" trust_principal="$2" description="$3"
    local existing
    existing=$(aws iam get-role --role-name "${role_name}" 2>&1 || true)
    if echo "$existing" | grep -q "NoSuchEntity"; then
        local trust_file
        trust_file="$(mktemp)"
        cat > "$trust_file" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "${trust_principal}"},
    "Action": "sts:AssumeRole"
  }]
}
EOF
        aws iam create-role --role-name "${role_name}" \
            --assume-role-policy-document "file://${trust_file}" \
            --description "${description}" >/dev/null
        rm -f "$trust_file"
        echo "   ✅ Role created: ${role_name}"
        NEW_ROLE_CREATED=1
    else
        echo "   ✅ Role exists: ${role_name}"
    fi
}

echo ""
echo "🔐 Ensuring ECS Express Mode IAM roles..."

ensure_role "${EXEC_ROLE_NAME}" "ecs-tasks.amazonaws.com" "ECS task execution role (pulls images, writes logs), shared across ECS services in this account"
aws iam attach-role-policy --role-name "${EXEC_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy 2>/dev/null || true

ensure_role "${INFRA_ROLE_NAME}" "ecs.amazonaws.com" "ECS Express Mode infrastructure provisioning role, shared across Express Mode services in this account"
aws iam attach-role-policy --role-name "${INFRA_ROLE_NAME}" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSInfrastructureRoleforExpressGatewayServices 2>/dev/null || true

ensure_role "${TASK_ROLE_NAME}" "ecs-tasks.amazonaws.com" "MemoryMesh Agent web app's own AWS permissions (invoke the AgentCore runtime)"
TASK_POLICY_FILE="$(mktemp)"
cat > "$TASK_POLICY_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
    "Resource": "${RUNTIME_ARN}*"
  }]
}
EOF
aws iam put-role-policy --role-name "${TASK_ROLE_NAME}" \
    --policy-name "${TASK_ROLE_NAME}-permissions" \
    --policy-document "file://${TASK_POLICY_FILE}"
rm -f "$TASK_POLICY_FILE"
echo "   ✅ Task role permissions attached"

# ECS itself needs its service-linked role to exist before it can create
# anything (cluster, service, load balancer, ...) — normally auto-created
# on first use, but that auto-creation doesn't always kick in, in which
# case create-express-gateway-service fails with "Unable to assume the
# service linked role." Ensure it explicitly.
if ! aws iam get-role --role-name AWSServiceRoleForECS >/dev/null 2>&1; then
    echo "   Creating ECS service-linked role (first time ECS is used in this account)..."
    aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com >/dev/null 2>&1 || true
    echo "   ✅ AWSServiceRoleForECS created"
    NEW_ROLE_CREATED=1
else
    echo "   ✅ AWSServiceRoleForECS already exists"
fi

EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE_NAME}"
INFRA_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${INFRA_ROLE_NAME}"
TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${TASK_ROLE_NAME}"

if [ "$NEW_ROLE_CREATED" = "1" ]; then
    echo "   ⏳ Waiting for new IAM roles to propagate (15 seconds)..."
    sleep 15
fi

# === Container definition, built via python so special characters in
#     COCKROACHDB_URL (&, ?, =) can't break the JSON ===
PRIMARY_CONTAINER_FILE="$(mktemp)"
python3 - "$IMAGE_URI" "$PORT" "$COCKROACHDB_URL" "$RUNTIME_ARN" "${JUDGE_ACCESS_PASSWORD:-}" "${JUDGE_SESSION_TTL_HOURS:-168}" "${COOKIE_SECURE:-true}" "${COCKROACHDB_CLUSTER_ID:-}" > "$PRIMARY_CONTAINER_FILE" <<'PYEOF'
import json
import sys

image, port, db_url, runtime_arn, judge_pw, ttl, cookie_secure, cluster_id = sys.argv[1:9]
env = [
    {"name": "COCKROACHDB_URL", "value": db_url},
    {"name": "AGENTCORE_RUNTIME_ARN", "value": runtime_arn},
    {"name": "AGENT_BACKEND_MODE", "value": "agentcore"},
    {"name": "JUDGE_SESSION_TTL_HOURS", "value": ttl},
    {"name": "COOKIE_SECURE", "value": cookie_secure},
]
if judge_pw:
    env.append({"name": "JUDGE_ACCESS_PASSWORD", "value": judge_pw})
if cluster_id:
    env.append({"name": "COCKROACHDB_CLUSTER_ID", "value": cluster_id})
print(json.dumps({"image": image, "containerPort": int(port), "environment": env}))
PYEOF

# === Create or update the Express Mode service ===
echo ""
echo "🚀 Deploying to Amazon ECS Express Mode..."
SERVICE_ARN="arn:aws:ecs:${REGION}:${ACCOUNT_ID}:service/default/${SERVICE_NAME}"

if aws ecs describe-express-gateway-service --service-arn "${SERVICE_ARN}" --region "${REGION}" >/dev/null 2>&1; then
    echo "   Updating existing service..."
    aws ecs update-express-gateway-service \
        --service-arn "${SERVICE_ARN}" \
        --region "${REGION}" \
        --primary-container "file://${PRIMARY_CONTAINER_FILE}" \
        --monitor-resources
else
    echo "   Creating new service..."
    aws ecs create-express-gateway-service \
        --service-name "${SERVICE_NAME}" \
        --region "${REGION}" \
        --execution-role-arn "${EXEC_ROLE_ARN}" \
        --infrastructure-role-arn "${INFRA_ROLE_ARN}" \
        --task-role-arn "${TASK_ROLE_ARN}" \
        --primary-container "file://${PRIMARY_CONTAINER_FILE}" \
        --health-check-path "/api/health" \
        --monitor-resources
fi
rm -f "$PRIMARY_CONTAINER_FILE"

echo ""
echo "🎉 Deployed!"
echo "================================="
echo "Your app should be live at:"
echo "   https://${SERVICE_NAME}.ecs.${REGION}.on.aws/"
echo ""
echo "(DNS/certificate propagation can take a minute or two after the status"
echo "turns ACTIVE. Check status any time with:"
echo "  aws ecs describe-express-gateway-service --service-arn ${SERVICE_ARN} --region ${REGION})"
