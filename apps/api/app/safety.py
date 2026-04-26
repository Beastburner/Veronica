from app.models import RiskLevel, ToolCallPlan

DANGEROUS_TERMS = {
    "delete",
    "remove",
    "rm ",
    "format",
    "drop database",
    "shutdown",
    "reboot",
    "exfiltrate",
    "credential",
    "api key",
    "private key",
}


def classify_risk(text: str) -> RiskLevel:
    lowered = text.lower()
    if any(term in lowered for term in DANGEROUS_TERMS):
        return RiskLevel.high
    if any(term in lowered for term in ["run", "execute", "deploy", "install", "write file"]):
        return RiskLevel.medium
    return RiskLevel.low


def confirmation_required(plan: ToolCallPlan) -> bool:
    return plan.risk in {RiskLevel.medium, RiskLevel.high}

