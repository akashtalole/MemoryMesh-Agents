import logging
from typing import Any, Dict, List, Optional

from src.agents import (
    AuditReviewerAgent,
    BaseAgent,
    BrokerMonitorAgent,
    CaseTriageAgent,
    ComplianceOfficerAgent,
    IntelAnalystAgent,
    MemoryOpsAgent,
    OrchestratorAgent,
    RiskMonitorAgent,
    SecurityMonitorAgent,
    SynthesizerAgent,
)

logger = logging.getLogger(__name__)


class AgentFactory:
    """Dynamic agent instantiation with state restoration"""

    SECURITY_MONITOR_NAME = "security_monitor"
    BROKER_MONITOR_NAME = "broker_monitor"
    RISK_MONITOR_NAME = "risk_monitor"
    INTEL_ANALYST_NAME = "intel_analyst"
    MEMORY_OPS_NAME = "memory_ops"
    COMPLIANCE_OFFICER_NAME = "compliance_officer"
    CASE_TRIAGE_NAME = "case_triage"
    AUDIT_REVIEWER_NAME = "audit_reviewer"
    ORCHESTRATOR_NAME = "orchestrator"
    SYNTHESIZER_NAME = "synthesizer"

    AGENT_CLASSES = {
        SECURITY_MONITOR_NAME: SecurityMonitorAgent,
        BROKER_MONITOR_NAME: BrokerMonitorAgent,
        RISK_MONITOR_NAME: RiskMonitorAgent,
        INTEL_ANALYST_NAME: IntelAnalystAgent,
        MEMORY_OPS_NAME: MemoryOpsAgent,
        COMPLIANCE_OFFICER_NAME: ComplianceOfficerAgent,
        CASE_TRIAGE_NAME: CaseTriageAgent,
        AUDIT_REVIEWER_NAME: AuditReviewerAgent,
        ORCHESTRATOR_NAME: OrchestratorAgent,
        SYNTHESIZER_NAME: SynthesizerAgent,
    }

    @staticmethod
    def create_agent(
        agent_name: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        session_id: Optional[str] = None,
    ) -> BaseAgent:
        """Factory method to create agents based on name"""
        logger.info(f"AgentFactory creating agent: {agent_name} with session_id: {session_id}")

        if agent_name not in AgentFactory.AGENT_CLASSES:
            raise ValueError(
                f"Unknown agent name: {agent_name}. "
                f"Available agents: {list(AgentFactory.AGENT_CLASSES.keys())}"
            )

        agent_class = AgentFactory.AGENT_CLASSES[agent_name]

        if messages:
            agent = agent_class().create_agent(messages=messages, session_id=session_id)
            logger.info(f"Restored {agent_class.__name__} with {len(messages)} messages")
        else:
            agent = agent_class().create_agent(session_id=session_id)
            logger.info(f"Created fresh {agent_class.__name__}")

        return agent
