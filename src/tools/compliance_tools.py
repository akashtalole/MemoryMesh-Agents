import json
import logging

from strands import tool

logger = logging.getLogger(__name__)

# Mock regulatory rulebook. In production this would be a real compliance
# ruleset (SEC/FINRA thresholds, house policy) held in its own table — the
# point here is that compliance_officer reasons against explicit, checkable
# rules rather than vague judgement calls.
REGULATORY_THRESHOLDS = {
    "wash_trading_risk": {
        "metric": "RiskScores.risk_score",
        "condition": ">= 0.5",
        "description": (
            "A risk score of 0.5 or higher on a stock-broker pair warrants a wash-trading review — "
            "repeated buy/sell activity by the same broker with no net economic change."
        ),
    },
    "anomaly_flag": {
        "metric": "RiskScores.anomaly_flag",
        "condition": "== 1",
        "description": "The system's own anomaly detector already flagged this stock-broker pair; treat as elevated priority.",
    },
    "concentration_risk": {
        "metric": "BrokerActivity.market_share_pct",
        "condition": ">= 25.0",
        "description": (
            "A single broker executing 25% or more of a symbol's daily volume is a concentration-risk "
            "flag — check for potential market manipulation or a data/reporting error."
        ),
    },
    "order_book_imbalance": {
        "metric": "OrderBook.depth_imbalance",
        "condition": "abs(value) >= 0.35",
        "description": "Bid/ask depth imbalance beyond ±0.35 can indicate spoofing or layering around that timestamp.",
    },
}


@tool
def get_regulatory_thresholds() -> str:
    """Return the regulatory/compliance thresholds this system checks trading
    activity against — wash-trading risk score, system anomaly flags, broker
    concentration risk, and order-book imbalance. Use this alongside
    run_report to decide whether specific data points constitute a
    compliance flag, and cite the exact threshold in your findings.

    Returns:
        str: JSON object of named rules, each with the metric it applies to,
        the breach condition, and a plain-language description.
    """
    logger.info("get_regulatory_thresholds called")
    return json.dumps(REGULATORY_THRESHOLDS, indent=2)
