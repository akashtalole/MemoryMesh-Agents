#!/bin/bash
set -euo pipefail

# Deploy MemoryMesh Agent to AWS Bedrock AgentCore by building the ARM64
# container image on AWS CodeBuild instead of locally. CodeBuild's
# aarch64 compute is native ARM64 — no Docker Desktop, no --platform
# emulation via QEMU, no local Docker install at all.
#
# Source comes straight from the public hackathon repo on GitHub (not a
# zip of your local working copy) — CodeBuild clones GITHUB_REPO_URL at
# GITHUB_BRANCH itself. Push your changes there first; this script builds
# whatever's on that branch right now, not local edits.
#
# One-time setup, before the first run: this AWS account/region needs a
# GitHub source credential registered so CodeBuild is allowed to clone from
# GitHub at all (required for CodeBuild's GITHUB source type even on a
# public repo). Either connect via the console (CodeBuild -> Settings ->
# Source providers -> Connect to GitHub) or run once:
#   aws codebuild import-source-credentials --server-type GITHUB \
#     --auth-type PERSONAL_ACCESS_TOKEN --token <your-github-PAT>
echo "🚀 Deploying MemoryMesh Agent to AWS Bedrock AgentCore via AWS CodeBuild..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="${PROJECT_DIR}/config"
BASE_SETTINGS="${CONFIG_DIR}/static-config.yaml"

GITHUB_REPO_URL="${GITHUB_REPO_URL:-https://github.com/akashtalole/MemoryMesh-Agents.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

if command -v yq >/dev/null 2>&1; then
    REGION=$(yq eval '.aws.region' "${BASE_SETTINGS}")
    ECR_REPO=$(yq eval '.runtime.ecr_repo' "${BASE_SETTINGS}")
else
    echo "⚠️  yq not found, using grep/sed fallback"
    REGION=$(grep "region:" "${BASE_SETTINGS}" | head -1 | sed 's/.*region: *\([^ #]*\).*/\1/')
    ECR_REPO=$(grep "ecr_repo:" "${BASE_SETTINGS}" | head -1 | sed 's/.*ecr_repo: *\([^ #]*\).*/\1/')
fi

CODEBUILD_PROJECT="${ECR_REPO}-build"
CODEBUILD_ROLE_NAME="memorymesh-agentcore-codebuild-role"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
if [ -z "$ACCOUNT_ID" ]; then
    echo "❌ Failed to get AWS Account ID. Please ensure AWS credentials are configured."
    exit 1
fi

echo "📝 Configuration:"
echo "   Region: ${REGION}"
echo "   ECR Repository: ${ECR_REPO}"
echo "   CodeBuild Project: ${CODEBUILD_PROJECT}"
echo "   Source: ${GITHUB_REPO_URL} @ ${GITHUB_BRANCH}"

# === PREREQUISITES SHARED WITH THE LOCAL-DOCKER PATH (IAM runtime role + ECR repo) ===
echo ""
echo "🔐 Ensuring AgentCore prerequisites (IAM role + ECR repo)..."
"${SCRIPT_DIR}/prerequisites.sh"

# === CODEBUILD SERVICE ROLE ===
echo ""
echo "🔐 Ensuring CodeBuild service role..."
CB_ROLE_EXISTS=$(aws iam get-role --role-name "${CODEBUILD_ROLE_NAME}" 2>&1 || true)

if echo "$CB_ROLE_EXISTS" | grep -q "NoSuchEntity"; then
    CB_TRUST_POLICY_FILE="$(mktemp)"
    cat > "$CB_TRUST_POLICY_FILE" <<EOF
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
        --assume-role-policy-document "file://${CB_TRUST_POLICY_FILE}" \
        --description "CodeBuild role for building MemoryMesh Agent's ARM64 AgentCore image" \
        --query 'Role.Arn' --output text)
    rm -f "$CB_TRUST_POLICY_FILE"
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
    {
      "Effect": "Allow",
      "Action": ["ecr:GetAuthorizationToken"],
      "Resource": "*"
    },
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

# === CODEBUILD PROJECT (source = the public GitHub repo, native ARM64 compute) ===
echo ""
echo "🏗️  Ensuring CodeBuild project..."
PROJECT_DEF_FILE="$(mktemp)"
cat > "$PROJECT_DEF_FILE" <<EOF
{
  "name": "${CODEBUILD_PROJECT}",
  "source": {
    "type": "GITHUB",
    "location": "${GITHUB_REPO_URL}",
    "buildspec": "buildspec.yml",
    "gitCloneDepth": 1
  },
  "sourceVersion": "${GITHUB_BRANCH}",
  "artifacts": { "type": "NO_ARTIFACTS" },
  "environment": {
    "type": "ARM_CONTAINER",
    "image": "aws/codebuild/amazonlinux2-aarch64-standard:3.0",
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
    if ! aws codebuild create-project --region "${REGION}" --cli-input-json "file://${PROJECT_DEF_FILE}" >/dev/null 2>/tmp/codebuild-create-err; then
        if grep -qi "source credentials\|OAuth\|source provider" /tmp/codebuild-create-err 2>/dev/null; then
            echo "   ❌ CodeBuild has no GitHub source credentials registered for this account/region yet."
            echo "      One-time fix — either connect via the console (CodeBuild -> Settings ->"
            echo "      Source providers -> Connect to GitHub), or run:"
            echo "        aws codebuild import-source-credentials --server-type GITHUB \\"
            echo "          --auth-type PERSONAL_ACCESS_TOKEN --token <your-github-PAT>"
            echo "      Then re-run this script."
        fi
        cat /tmp/codebuild-create-err >&2
        rm -f /tmp/codebuild-create-err
        rm -f "$PROJECT_DEF_FILE"
        exit 1
    fi
    rm -f /tmp/codebuild-create-err
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
echo "🔨 Starting CodeBuild build (native ARM64 — no local Docker involved)..."

MAX_ATTEMPTS=3
ATTEMPT=1
STATUS=""
BUILD_ID=""
while [ "$ATTEMPT" -le "$MAX_ATTEMPTS" ]; do
    BUILD_ID=$(aws codebuild start-build --project-name "${CODEBUILD_PROJECT}" --region "${REGION}" \
        --source-version "${GITHUB_BRANCH}" \
        --query 'build.id' --output text)
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

# === DEPLOY TO AGENTCORE (same script the local-Docker path uses) ===
echo ""
echo "🚀 Deploying to AgentCore runtime..."
cd "${SCRIPT_DIR}"

if python3 deploy-runtime.py; then
    echo ""
    echo "🎉 Deployment Complete!"
    echo "================================="
    echo "✅ Image built on CodeBuild (ARM64, no local Docker used)"
    echo "✅ AgentCore runtime deployed"
    echo ""
    echo "📋 Next steps:"
    echo "   1. Check config/dynamic-config.yaml for the runtime ARN"
    echo "   2. Set ANTHROPIC_API_KEY and COCKROACHDB_URL on the runtime (not baked into the image)"
    echo "   3. make dev   # now proxies chat requests to the deployed runtime"
else
    echo ""
    echo "❌ Runtime deployment failed — see the error messages above"
    exit 1
fi
