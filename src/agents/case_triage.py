import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.prompts.system_prompts import CASE_TRIAGE_AGENT_PROMPT
from src.tools.memory_tools import recall_similar_investigations

logger = logging.getLogger(__name__)


class CaseTriageAgent(BaseAgent):
    """Assigns an investigation priority by explicitly querying CockroachDB's
    long-term case memory (distributed vector index) for how similar
    patterns were resolved before.

    Unlike `recall_case_memory` (an automatic graph node that runs on every
    request), this agent decides *when* memory recall is relevant and reads
    the results itself, tool-call style.
    """

    def __init__(self):
        logger.info("Initializing CaseTriageAgent")
        super().__init__()
        self.model = get_model(max_tokens=4000)
        self.agent_name = "case_triage"
        self.system_prompt = CASE_TRIAGE_AGENT_PROMPT
        self.tools = [recall_similar_investigations]
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating CaseTriageAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
