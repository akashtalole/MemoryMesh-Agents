"""LangGraph workflow: orchestrator -> specialists -> synthesizer, wrapped by
two CockroachDB-backed memory steps.

    recall_case_memory -> orchestrator -> [specialists...] -> synthesizer -> persist_case_memory -> END

* Every node transition is checkpointed into CockroachDB (`AsyncCockroachDBSaver`) —
  this is what previously came from AgentCore Memory / an in-process MemorySaver.
* `recall_case_memory` runs a distributed vector-index similarity search over
  every past investigation (not just this thread) before the orchestrator
  even sees the query, so routing and synthesis can build on precedent.
* `persist_case_memory` embeds the synthesizer's finding and writes it back
  into the same vector table, so the system's memory compounds with every
  investigation instead of resetting per session.
* Each completed turn is also appended to a durable, human-readable
  CockroachDB chat-history table for audit purposes.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from src.agents.agent_factory import AgentFactory
from src.memory.case_memory import init_case_memory, recall_similar_cases, record_case
from src.memory.chat_history import record_turn
from src.memory.checkpointer import build_checkpointer
from src.utils.llm_utils import parse_agent_json_response, safe_log_text
from src.utils.session_manager import SessionManager
from src.utils.stream import langgraph_stream_writer

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    query_text: str
    session_id: Optional[str]
    # Orchestration specific state
    agent_task_map: Optional[Dict[str, str]]
    required_agents: Optional[List[str]]
    orchestrator_context: Optional[Dict[str, Any]]
    # Long-term memory recalled from CockroachDB before routing
    similar_cases: Optional[List[Dict[str, Any]]]
    case_id: Optional[str]
    # Strands Agent State for Dynamic Creation
    orchestrator_state: Optional[Dict[str, Any]]
    security_monitor_state: Optional[Dict[str, Any]]
    broker_monitor_state: Optional[Dict[str, Any]]
    risk_monitor_state: Optional[Dict[str, Any]]
    intel_analyst_state: Optional[Dict[str, Any]]
    memory_ops_state: Optional[Dict[str, Any]]
    compliance_officer_state: Optional[Dict[str, Any]]
    case_triage_state: Optional[Dict[str, Any]]
    audit_reviewer_state: Optional[Dict[str, Any]]
    synthesizer_state: Optional[Dict[str, Any]]
    # Insights from each agent
    security_monitor_insights: Optional[Dict[str, Any]]
    broker_monitor_insights: Optional[Dict[str, Any]]
    risk_monitor_insights: Optional[Dict[str, Any]]
    intel_analyst_insights: Optional[Dict[str, Any]]
    memory_ops_insights: Optional[Dict[str, Any]]
    compliance_officer_insights: Optional[Dict[str, Any]]
    case_triage_insights: Optional[Dict[str, Any]]
    audit_reviewer_insights: Optional[Dict[str, Any]]
    synthesizer_insights: Optional[str]
    current_agent_index: Optional[int]


class Workflow:
    """Multi-agent market-surveillance workflow with CockroachDB as the
    single persistent memory layer (checkpoints, chat history, case memory).

    Construct with `await Workflow.create()` — building the CockroachDB
    checkpointer and case-memory vector store requires async setup, so this
    class cannot be fully initialised from a plain `__init__`.
    """

    def __init__(self):
        self.session_manager = SessionManager()
        self.checkpointer = None
        self.graph = None

    @classmethod
    async def create(cls) -> "Workflow":
        self = cls()
        self.checkpointer = await build_checkpointer()
        await init_case_memory()
        self.graph = self._create_workflow()
        logger.info("Workflow ready (CockroachDB checkpointer + case memory initialised)")
        return self

    # ------------------------------------------------------------------
    # Memory context helpers
    # ------------------------------------------------------------------

    def build_orchestrator_context(self, state: AgentState) -> str:
        if state.get("orchestrator_context"):
            prev_context = state["orchestrator_context"]
            logger.info(f"Building orchestrator context from previous execution: {safe_log_text(prev_context)}")
            return (
                "FOLLOWING IS FINAL RESULT FROM YOUR PREVIOUS ORCHESTRATION.\n"
                "USE THE CONTEXT TO PROCESS THE CURRENT QUERY.\n"
                f"PREVIOUS EXECUTION CONTEXT: {prev_context}"
            )
        return ""

    @staticmethod
    def build_memory_context(state: AgentState) -> str:
        """Render the CockroachDB case-memory recall as prompt context."""
        similar_cases = state.get("similar_cases") or []
        if not similar_cases:
            return ""
        lines = ["PRIOR SIMILAR CASES (recalled from CockroachDB long-term case memory):"]
        for case in similar_cases:
            lines.append(
                f"- [recorded {case.get('recorded_at', 'unknown time')}, "
                f"similarity={case.get('score')}] Q: {case.get('query')}\n  {case.get('findings')}"
            )
        return "\n".join(lines)

    def get_agent_instance(self, state: AgentState, agent_state_name: str, agent_name: str):
        session_id = state.get("session_id")
        if state.get(agent_state_name) and state[agent_state_name].get("messages"):
            messages = state[agent_state_name]["messages"]
            return AgentFactory.create_agent(agent_name=agent_name, messages=messages, session_id=session_id)
        return AgentFactory.create_agent(agent_name=agent_name, session_id=session_id)

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    async def recall_case_memory(self, state: AgentState) -> AgentState:
        """Entry node: semantic search over every past investigation stored
        in CockroachDB's case_memory table via its distributed C-SPANN index.
        """
        query_text = state["query_text"]
        try:
            similar_cases = await recall_similar_cases(query_text)
        except Exception as e:
            logger.warning(f"Case memory recall failed, continuing without it: {e}")
            similar_cases = []

        if similar_cases:
            logger.info(f"Recalled {len(similar_cases)} similar case(s) from CockroachDB case memory")

        return {"similar_cases": similar_cases}

    async def orchestrator(self, state: AgentState) -> AgentState:
        logger.info(f"Orchestrator processing query: {state['query_text']}")

        context_parts = []
        prior_context = self.build_orchestrator_context(state)
        if prior_context:
            context_parts.append(prior_context)
        memory_context = self.build_memory_context(state)
        if memory_context:
            context_parts.append(memory_context)

        if context_parts:
            prompt = (
                "\n\n".join(context_parts)
                + f"\n\nNEW QUERY: {state['query_text']}\n"
                "Based on the context above, determine which agents are needed for this new query. "
                "Avoid redundant analysis if prior context already fully addresses it."
            )
        else:
            prompt = state["query_text"]

        agent = self.get_agent_instance(state=state, agent_state_name="orchestrator_state",
                                        agent_name=AgentFactory.ORCHESTRATOR_NAME)

        final_response = await langgraph_stream_writer(agent, prompt, AgentFactory.ORCHESTRATOR_NAME)
        logger.info(f"Orchestrator streaming output: {safe_log_text(final_response)}")

        required_agents = []
        agent_task_map = {}
        try:
            agent_json_output = parse_agent_json_response(final_response)
            agent_tasks = agent_json_output.get("agent_tasks", []) if agent_json_output else []
            if agent_tasks:
                agent_task_map = {task["agent"]: task["task"] for task in agent_tasks}
                required_agents = [task["agent"] for task in agent_tasks]
        except Exception as e:
            logger.warning(f"No structured task returned from orchestrator or error parsing: {e}")

        logger.info(f"=====> Required Agents: {required_agents}")

        return {
            "orchestrator_state": {"messages": agent.messages},
            "agent_task_map": agent_task_map,
            "required_agents": required_agents,
            "current_agent_index": 0 if required_agents else None,
            "security_monitor_insights": None,
            "broker_monitor_insights": None,
            "risk_monitor_insights": None,
            "intel_analyst_insights": None,
            "memory_ops_insights": None,
            "compliance_officer_insights": None,
            "case_triage_insights": None,
            "audit_reviewer_insights": None,
            "synthesizer_insights": None,
            "orchestrator_context": None,
        }

    async def _run_specialist(
        self, state: AgentState, agent_name: str, state_key: str, extra_context: Optional[str] = None
    ) -> AgentState:
        logger.info(f"====>{agent_name} performing analysis...")
        agent_task_map = state.get("agent_task_map", {})
        current_task = agent_task_map.get(agent_name)
        prompt = current_task if current_task else state["query_text"]
        if extra_context:
            prompt = f"{prompt}\n\n{extra_context}"

        agent = self.get_agent_instance(state=state, agent_state_name=f"{state_key}_state", agent_name=agent_name)
        final_response = await langgraph_stream_writer(agent, prompt, agent_name)
        logger.info(f"{agent_name} streaming output: {safe_log_text(final_response)}")

        try:
            agent_json_output = parse_agent_json_response(final_response)
            business_insights = agent_json_output.get("business_insights", []) if agent_json_output else final_response
        except Exception as e:
            logger.warning(f"No structured response from {agent_name} or error parsing: {e}")
            business_insights = f"No explicit insight available, storing raw response {final_response}"

        return {
            f"{state_key}_state": {"messages": agent.messages},
            f"{state_key}_insights": {"task": current_task, "business_insights": business_insights},
            "current_agent_index": state.get("current_agent_index", 0) + 1,
        }

    async def security_monitor(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.SECURITY_MONITOR_NAME, "security_monitor")

    async def broker_monitor(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.BROKER_MONITOR_NAME, "broker_monitor")

    async def risk_monitor(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.RISK_MONITOR_NAME, "risk_monitor")

    async def intel_analyst(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.INTEL_ANALYST_NAME, "intel_analyst")

    async def memory_ops(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.MEMORY_OPS_NAME, "memory_ops")

    async def compliance_officer(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.COMPLIANCE_OFFICER_NAME, "compliance_officer")

    async def case_triage(self, state: AgentState) -> AgentState:
        return await self._run_specialist(state, AgentFactory.CASE_TRIAGE_NAME, "case_triage")

    async def audit_reviewer(self, state: AgentState) -> AgentState:
        # get_session_audit_trail needs an exact session_id — supply it
        # deterministically instead of trusting the LLM to carry it through
        # the orchestrator's task text.
        extra_context = f"(current session_id: {state.get('session_id')})"
        return await self._run_specialist(
            state, AgentFactory.AUDIT_REVIEWER_NAME, "audit_reviewer", extra_context=extra_context
        )

    def build_synthesizer_context(self, state: AgentState) -> str:
        context_parts = [f"Original query: {state['query_text']}"]

        memory_context = self.build_memory_context(state)
        if memory_context:
            context_parts.append(memory_context)

        for label, key in [
            ("SECURITY MONITOR ANALYSIS", "security_monitor_insights"),
            ("RISK MONITOR ANALYSIS", "risk_monitor_insights"),
            ("INTEL ANALYST ANALYSIS", "intel_analyst_insights"),
            ("BROKER MONITOR ANALYSIS", "broker_monitor_insights"),
            ("MEMORY OPS ANALYSIS", "memory_ops_insights"),
            ("COMPLIANCE OFFICER ANALYSIS", "compliance_officer_insights"),
            ("CASE TRIAGE ANALYSIS", "case_triage_insights"),
            ("AUDIT REVIEWER ANALYSIS", "audit_reviewer_insights"),
        ]:
            if state.get(key):
                context_parts.append(f"{label}: {state[key]}")

        return "\n\n".join(context_parts)

    async def synthesizer(self, state: AgentState) -> AgentState:
        logger.info("=====>Synthesizing final response...")
        context = self.build_synthesizer_context(state)
        prompt = f"Synthesize the following analysis results into a comprehensive response:\n\n{context}"

        agent = self.get_agent_instance(state=state, agent_state_name="synthesizer_state",
                                        agent_name=AgentFactory.SYNTHESIZER_NAME)

        final_response = await langgraph_stream_writer(agent, prompt, AgentFactory.SYNTHESIZER_NAME)
        logger.info(f"Synthesizer streaming output: {safe_log_text(final_response)}")

        orchestrator_context = {
            "query_text": state["query_text"],
            "required_agents": state.get("required_agents", []),
            "final_result": final_response,
        }

        return {
            "synthesizer_insights": final_response,
            "orchestrator_context": orchestrator_context,
            "synthesizer_state": {"messages": agent.messages},
        }

    async def persist_case_memory(self, state: AgentState) -> AgentState:
        """Terminal node: embed this investigation's finding and write it
        into CockroachDB's case_memory vector table so future queries can
        recall it. This is what makes the memory compound across sessions.
        """
        summary = state.get("synthesizer_insights")
        if not summary:
            return {}

        summary_text = summary if isinstance(summary, str) else json.dumps(summary)
        try:
            case_id = await record_case(
                session_id=state.get("session_id") or "unknown-session",
                query_text=state["query_text"],
                required_agents=state.get("required_agents") or [],
                summary=summary_text,
            )
        except Exception as e:
            logger.error(f"Failed to persist case memory: {e}")
            case_id = None

        return {"case_id": case_id}

    def route_analysts(self, state: AgentState) -> str:
        required_agents = state.get("required_agents", [])
        current_index = state.get("current_agent_index", 0)

        if not required_agents:
            return END

        if current_index < len(required_agents):
            return required_agents[current_index]

        return AgentFactory.SYNTHESIZER_NAME

    def _create_workflow(self) -> StateGraph:
        logger.info("Creating LangGraph workflow...")
        workflow = StateGraph(AgentState)

        workflow.add_node("recall_case_memory", self.recall_case_memory)
        workflow.add_node(AgentFactory.ORCHESTRATOR_NAME, self.orchestrator)
        workflow.add_node(AgentFactory.SECURITY_MONITOR_NAME, self.security_monitor)
        workflow.add_node(AgentFactory.BROKER_MONITOR_NAME, self.broker_monitor)
        workflow.add_node(AgentFactory.RISK_MONITOR_NAME, self.risk_monitor)
        workflow.add_node(AgentFactory.INTEL_ANALYST_NAME, self.intel_analyst)
        workflow.add_node(AgentFactory.MEMORY_OPS_NAME, self.memory_ops)
        workflow.add_node(AgentFactory.COMPLIANCE_OFFICER_NAME, self.compliance_officer)
        workflow.add_node(AgentFactory.CASE_TRIAGE_NAME, self.case_triage)
        workflow.add_node(AgentFactory.AUDIT_REVIEWER_NAME, self.audit_reviewer)
        workflow.add_node(AgentFactory.SYNTHESIZER_NAME, self.synthesizer)
        workflow.add_node("persist_case_memory", self.persist_case_memory)

        specialists = [
            AgentFactory.SECURITY_MONITOR_NAME,
            AgentFactory.BROKER_MONITOR_NAME,
            AgentFactory.RISK_MONITOR_NAME,
            AgentFactory.INTEL_ANALYST_NAME,
            AgentFactory.MEMORY_OPS_NAME,
            AgentFactory.COMPLIANCE_OFFICER_NAME,
            AgentFactory.CASE_TRIAGE_NAME,
            AgentFactory.AUDIT_REVIEWER_NAME,
        ]
        all_targets = {name: name for name in specialists} | {
            AgentFactory.SYNTHESIZER_NAME: AgentFactory.SYNTHESIZER_NAME,
            END: END,
        }

        workflow.add_edge("recall_case_memory", AgentFactory.ORCHESTRATOR_NAME)
        workflow.add_conditional_edges(AgentFactory.ORCHESTRATOR_NAME, self.route_analysts, all_targets)
        for name in specialists:
            workflow.add_conditional_edges(name, self.route_analysts, all_targets)

        workflow.add_edge(AgentFactory.SYNTHESIZER_NAME, "persist_case_memory")
        workflow.add_edge("persist_case_memory", END)

        workflow.set_entry_point("recall_case_memory")

        graph = workflow.compile(checkpointer=self.checkpointer)
        logger.info("LangGraph workflow compiled successfully.")
        return graph

    # ------------------------------------------------------------------
    # Public streaming entrypoint
    # ------------------------------------------------------------------

    async def stream_query(self, session_id: str, prompt: str, actor_id: str = "default-actor"):
        """Process a query for a given session, streaming SSE-formatted chunks."""
        session_info = self.session_manager.get_session_info(session_id)
        if not session_info:
            logger.warning(f"Session ID not found: {session_id}. Creating new session.")
            created_session_id = self.session_manager.create_session(
                user_id="auto_created", session_name=f"auto_{session_id[:12]}", session_id=session_id
            )
            session_info = self.session_manager.get_session_info(created_session_id)

        self.session_manager.update_session_activity(session_id)
        logger.info(f"Streaming query for session {session_id} (actor {actor_id}): {safe_log_text(prompt)}")

        # thread_id is all AsyncCockroachDBSaver needs to scope checkpoints —
        # unlike AgentCoreMemorySaver, no separate actor_id is required.
        config = {"configurable": {"thread_id": session_id}}
        initial_state = {"session_id": session_id, "query_text": prompt}

        try:
            async for chunk in self.graph.astream(initial_state, config=config, stream_mode="custom"):
                try:
                    yield f"data: {json.dumps(chunk)}\n\n"
                except (TypeError, ValueError):
                    yield f"data: {str(chunk)}\n\n"
        except Exception as e:
            logger.error(f"Error processing query for session {session_id}: {e}")
            yield f"data: {json.dumps({'error': str(e), 'session_id': session_id})}\n\n"
            return

        # Durable, human-readable audit record — independent of the LangGraph
        # checkpoint blob, queryable directly from the CockroachDB console.
        try:
            final_state = await self.graph.aget_state(config)
            final_answer = final_state.values.get("synthesizer_insights") if final_state else None
            if final_answer:
                answer_text = final_answer if isinstance(final_answer, str) else json.dumps(final_answer)
                # record_turn uses the sync CockroachDBChatMessageHistory API —
                # push it off the event loop so it can't stall other requests.
                await asyncio.to_thread(record_turn, session_id, prompt, answer_text)
        except Exception as e:
            logger.warning(f"Could not record chat history turn: {e}")
