from src.utils.file_utils import load_prompt_from_file

# Agent Prompts
SECURITY_MONITOR_AGENT_PROMPT = load_prompt_from_file("agents/security_monitor")
BROKER_MONITOR_AGENT_PROMPT = load_prompt_from_file("agents/broker_monitor")
RISK_MONITOR_AGENT_PROMPT = load_prompt_from_file("agents/risk_monitor")
INTEL_ANALYST_AGENT_PROMPT = load_prompt_from_file("agents/intel_analyst")
MEMORY_OPS_AGENT_PROMPT = load_prompt_from_file("agents/memory_ops")
COMPLIANCE_OFFICER_AGENT_PROMPT = load_prompt_from_file("agents/compliance_officer")
CASE_TRIAGE_AGENT_PROMPT = load_prompt_from_file("agents/case_triage")
AUDIT_REVIEWER_AGENT_PROMPT = load_prompt_from_file("agents/audit_reviewer")
ORCHESTRATOR_AGENT_PROMPT = load_prompt_from_file("agents/orchestrator")
