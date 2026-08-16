import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.prompts.system_prompts import AUDIT_REVIEWER_AGENT_PROMPT
from src.tools.memory_tools import get_session_audit_trail

logger = logging.getLogger(__name__)


class AuditReviewerAgent(BaseAgent):
    """Summarizes the durable, human-readable audit trail for a session by
    reading CockroachDB's message_store table directly — independent of any
    internal LangGraph checkpoint state.
    """

    def __init__(self):
        logger.info("Initializing AuditReviewerAgent")
        super().__init__()
        self.model = get_model(max_tokens=4000)
        self.agent_name = "audit_reviewer"
        self.system_prompt = AUDIT_REVIEWER_AGENT_PROMPT
        self.tools = [get_session_audit_trail]
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating AuditReviewerAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
