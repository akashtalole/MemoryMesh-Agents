import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.prompts.system_prompts import ORCHESTRATOR_AGENT_PROMPT

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """Routes user queries to the appropriate set of specialist agents.

    No data-access tools — the orchestrator reasons over the query text (plus
    any prior-similar-cases context recalled from CockroachDB case memory)
    and returns a JSON routing decision listing which specialists to invoke.
    """

    def __init__(self):
        logger.info("Initializing OrchestratorAgent")
        super().__init__()
        self.model = get_model(max_tokens=2000)
        self.agent_name = "orchestrator"
        self.system_prompt = ORCHESTRATOR_AGENT_PROMPT
        self.tools = []
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating OrchestratorAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
