import logging

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for agents with common functionality"""

    def __init__(self):
        logger.info("Initializing BaseAgent")
        self.model = None
        self.agent_name = None
        self.system_prompt = None
        self.tools = []
        self.callback_handler = None
        logger.debug("BaseAgent initialization completed")

    def create_agent(self, messages=None, session_id=None):
        """Create an agent with specified model and tools"""
        raise NotImplementedError("Subclasses should implement this method")

    def execute(self, query, session_id=None):
        """Execute single predefined query"""
        logger.info("Starting execute query mode")
        agent = self.create_agent(session_id=session_id)

        logger.info(f"Executing query: {query}")
        try:
            result = agent(query)
            logger.info(f"Query processed successfully: {type(result)}")
            return result
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return None
