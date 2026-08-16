import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.prompts.system_prompts import COMPLIANCE_OFFICER_AGENT_PROMPT
from src.tools.compliance_tools import get_regulatory_thresholds
from src.tools.extraction_tools import get_report_list, get_report_schema, run_report

logger = logging.getLogger(__name__)


class ComplianceOfficerAgent(BaseAgent):
    """Checks trading data against explicit regulatory thresholds.

    Has access to: TradeActivity, BrokerActivity, RiskScores reports, plus
    the system's own rulebook (get_regulatory_thresholds). Issues a
    CLEAR/FLAGGED verdict per rule checked, citing the exact numbers.
    """

    def __init__(self):
        logger.info("Initializing ComplianceOfficerAgent")
        super().__init__()
        self.model = get_model(max_tokens=6000)
        self.agent_name = "compliance_officer"
        self.system_prompt = COMPLIANCE_OFFICER_AGENT_PROMPT
        self.tools = [get_report_list, get_report_schema, run_report, get_regulatory_thresholds]
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating ComplianceOfficerAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
