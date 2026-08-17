#!/bin/bash
# Provision a CockroachDB Cloud cluster for MemoryMesh Agent using the
# agent-ready `ccloud` CLI — noun-verb commands, JSON output, service-account
# based auth. This is one of this project's two required CockroachDB tools
# (the other is the distributed vector index used by src/memory/case_memory.py).
#
# What this does:
#   1. Confirms `ccloud` is installed and you're authenticated
#   2. Creates a free/basic cluster (or reuses one you name)
#   3. Creates a SQL user + prints a ready-to-use connection string
#
# ccloud's exact flags can shift between CLI versions — this script prints
# every command before running it and falls back to `--help` guidance if a
# step doesn't match your installed version, rather than failing silently.
set -euo pipefail

CLUSTER_NAME="${CCLOUD_CLUSTER_NAME:-memorymesh-agent}"
CLOUD_PROVIDER="${CCLOUD_CLOUD_PROVIDER:-AWS}"
REGION="${CCLOUD_REGION:-us-east-1}"
SQL_USER="${CCLOUD_SQL_USER:-memorymesh}"

if ! command -v ccloud >/dev/null 2>&1; then
    echo "❌ ccloud CLI not found."
    echo "   Install: https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started"
    exit 1
fi

echo "🔐 Checking ccloud auth..."
if ! ccloud auth list >/dev/null 2>&1; then
    echo "   Not logged in — launching 'ccloud auth login'..."
    ccloud auth login
fi

echo ""
echo "🐘 Creating CockroachDB Cloud cluster '${CLUSTER_NAME}' (${CLOUD_PROVIDER}/${REGION})..."
echo "   \$ ccloud cluster create ${CLUSTER_NAME} --provider ${CLOUD_PROVIDER} --region ${REGION} --plan basic --output json"
if ! ccloud cluster create "${CLUSTER_NAME}" \
    --provider "${CLOUD_PROVIDER}" \
    --region "${REGION}" \
    --plan basic \
    --output json > /tmp/memorymesh-cluster-create.json 2>/tmp/memorymesh-cluster-create.err; then
    echo "⚠️  'ccloud cluster create' did not succeed with the flags this script assumes."
    echo "   Run 'ccloud cluster create --help' to check the flags for your installed"
    echo "   ccloud version, or provision the cluster from the CockroachDB Cloud Console"
    echo "   instead — either way, this script continues at step 3 (SQL user + connection"
    echo "   string) once you point CLUSTER_NAME at an existing cluster."
    cat /tmp/memorymesh-cluster-create.err || true
else
    echo "   ✅ Cluster create request submitted"
    cat /tmp/memorymesh-cluster-create.json
fi

echo ""
echo "⏳ Checking cluster status (ccloud cluster list --output json)..."
ccloud cluster list --output json | tee /tmp/memorymesh-cluster-list.json || true

echo ""
echo "👤 Creating SQL user '${SQL_USER}'..."
echo "   \$ ccloud cluster sql-user create ${SQL_USER} --cluster ${CLUSTER_NAME} --output json"
ccloud cluster sql-user create "${SQL_USER}" --cluster "${CLUSTER_NAME}" --output json \
    || echo "   ⚠️  Adjust to match 'ccloud cluster sql-user create --help' for your version."

echo ""
echo "🔗 Fetching connection parameters..."
echo "   \$ ccloud cluster sql ${CLUSTER_NAME} --connection-params --output json"
ccloud cluster sql "${CLUSTER_NAME}" --connection-params --output json \
    || echo "   ⚠️  Adjust to match 'ccloud cluster sql --help' for your version."

echo ""
echo "🎉 Done. Copy the connection string above into COCKROACHDB_URL in your .env"
echo "   (swap in the SQL user's password from the Cloud Console -> SQL Users),"
echo "   then run: make init-memory"
