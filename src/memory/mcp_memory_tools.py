"""CockroachDB Cloud Managed MCP Server as an agent tool source.

Wires the memory_ops specialist agent directly to
https://cockroachlabs.cloud/mcp so it can introspect the very cluster that
backs its own memory — table schemas, row counts, running queries — using
the server's safe-by-default read-only tools (list_tables, get_table_schema,
select_query, show_running_queries, ...). No custom proxy, no bespoke SQL
client: authentication is a single service-account bearer token, and the
Strands `MCPClient` handles tool discovery + invocation.
"""

import logging
import os

logger = logging.getLogger(__name__)


def cockroachdb_cloud_mcp_client():
    """Build a Strands MCPClient bound to the CockroachDB Cloud MCP server.

    Returns None (rather than raising) when no service-account key is
    configured, so the memory_ops agent degrades gracefully to "MCP tools
    unavailable" instead of failing the whole workflow to build.
    """
    api_key = os.getenv("COCKROACHDB_MCP_API_KEY")
    if not api_key:
        logger.warning(
            "COCKROACHDB_MCP_API_KEY not set — memory_ops agent will run "
            "without CockroachDB Cloud MCP introspection tools"
        )
        return None

    from mcp.client.streamable_http import streamablehttp_client
    from strands.tools.mcp import MCPClient

    url = os.getenv("COCKROACHDB_MCP_URL", "https://cockroachlabs.cloud/mcp")
    headers = {"Authorization": f"Bearer {api_key}"}

    cluster_id = os.getenv("COCKROACHDB_MCP_CLUSTER_ID")
    if cluster_id:
        headers["mcp-cluster-id"] = cluster_id
        logger.info(f"CockroachDB Cloud MCP client scoped to cluster_id={cluster_id}")
    else:
        logger.info("CockroachDB Cloud MCP client scoped to all accessible clusters")

    return MCPClient(lambda: streamablehttp_client(url=url, headers=headers))
