import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.memory.mcp_memory_tools import cockroachdb_cloud_mcp_client
from src.prompts.system_prompts import MEMORY_OPS_AGENT_PROMPT

logger = logging.getLogger(__name__)


class MemoryOpsAgent(BaseAgent):
    """Answers questions about the surveillance system's OWN memory.

    Unique among the specialists: its tool is not the mock market-data
    catalog but the CockroachDB Cloud Managed MCP Server, connected directly
    to the same cluster backing the workflow's checkpoints, chat history, and
    case memory — turning "how much do we remember, and about what?" into a
    question the agent can actually answer by querying its own memory store.
    """

    def __init__(self):
        logger.info("Initializing MemoryOpsAgent")
        super().__init__()
        self.model = get_model(max_tokens=4000)
        self.agent_name = "memory_ops"
        self.system_prompt = MEMORY_OPS_AGENT_PROMPT

        mcp_client = cockroachdb_cloud_mcp_client()
        self.tools = [mcp_client] if mcp_client else []
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating MemoryOpsAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
