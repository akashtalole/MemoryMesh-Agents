import logging
import os

from strands import Agent

from src.agents.base_agent import BaseAgent
from src.agents.model_provider import get_model

logger = logging.getLogger(__name__)


class SynthesizerAgent(BaseAgent):
    """Combines specialist agent insights into a structured final response.

    No tools — reads the accumulated insights from all specialists (and any
    recalled prior-case context) in the LangGraph state and synthesises them
    into a coherent, factual summary. That summary is what gets embedded and
    written back into CockroachDB case memory for future recall.
    """

    def __init__(self):
        logger.info("Initializing SynthesizerAgent")
        super().__init__()
        self.model = get_model(max_tokens=4000)
        self.agent_name = "synthesizer"

        default_prompt = """
        You are a market surveillance data synthesizer that consolidates specialist analysis into objective assessments.

        SYNTHESIS PROTOCOL:
        - Consolidate specialist analyst findings into structured, factual summaries
        - Present information using neutral, descriptive language without emotional indicators
        - Base all statements on data and evidence provided by specialist analysts
        - If a "PRIOR SIMILAR CASES" block is present, explicitly note whether this
          investigation confirms, contradicts, or extends what was found previously

        CONTENT REQUIREMENTS:
        - Extract key findings from specialist analysis and present as structured bullet points
        - Include specific metrics, timestamps, and quantitative data where available
        - Note any analytical limitations or data quality considerations
        - Acknowledge conflicting specialist views without taking sides

        LANGUAGE STANDARDS:
        - Use factual, descriptive terminology (e.g., "analysis indicates" rather than "clearly shows")
        - Avoid superlatives, emotional language, or value-laden terms
        - Present observations neutrally (e.g., "trading volume increased by X%" rather than "volume exploded")
        - Use conditional language when appropriate (e.g., "appears to indicate," "suggests")

        OUTPUT FORMAT:
        - Structure response as bullet points addressing the user's specific question
        - Lead with factual observations before analytical conclusions
        - Reference data sources and timeframes for all significant findings
        - Maintain consistent, professional terminology throughout
        - End with a one-line "CASE SUMMARY:" sentence suitable for storing as a
          searchable memory record of this investigation
        """

        self.system_prompt = os.getenv("SYNTHESIZER_PROMPT", default_prompt)
        self.tools = []
        self.callback_handler = None

    def create_agent(self, messages=None, session_id=None):
        logger.info(f"Creating SynthesizerAgent with session_id: {session_id}")
        trace_attributes = None
        if session_id:
            trace_attributes = {"session_id": session_id, "agent_name": self.agent_name}
        agent = Agent(
            model=self.model, messages=messages, name=self.agent_name,
            system_prompt=self.system_prompt, tools=self.tools,
            callback_handler=self.callback_handler, trace_attributes=trace_attributes
        )
        return agent
