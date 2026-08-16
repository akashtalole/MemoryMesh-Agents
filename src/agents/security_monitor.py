import logging

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model
from src.prompts.system_prompts import SECURITY_MONITOR_AGENT_PROMPT
from src.tools.extraction_tools import get_report_list, get_report_schema, run_report

logger = logging.getLogger(__name__)


class SecurityMonitorAgent(BaseAgent):
    """Analyses single-security intraday trading activity for anomalies.

    Has access to: TradeActivity, PriceBars, OrderBook, VolumeProfile reports.
    Detects wash trades, spoofing, and front-running patterns for a single symbol
    within a narrow time window.
    """

    def __init__(self):
        logger.info("Initializing SecurityMonitorAgent")
        super().__init__()
        self.model = get_model(max_tokens=8000)
        self.agent_name = "security_monitor"
        self.system_prompt = SECURITY_MONITOR_AGENT_PROMPT
        self.tools = [get_report_list, get_report_schema, run_report]
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating SecurityMonitorAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
