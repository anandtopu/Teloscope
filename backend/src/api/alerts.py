"""AgentLens — Alerts API"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ..core.logging import get_logger
from ..models.trace import Alert, AlertRule, AlertSeverity

router = APIRouter()
logger = get_logger("api.alerts")

# In-memory rule store (replace with DB in production)
_rules: Dict[str, AlertRule] = {}
_fired_alerts: List[Alert] = []


class CreateRuleRequest(BaseModel):
    org_id: str
    project_id: str
    name: str
    description: Optional[str] = None
    severity: AlertSeverity = AlertSeverity.WARNING
    metric: str
    operator: str
    threshold: float
    window_minutes: int = 5
    agent_filter: Optional[str] = None
    notify_slack: bool = False
    notify_email: List[str] = []
    notify_pagerduty: bool = False


@router.get("/rules")
async def list_rules(org_id: str = Query(...), project_id: str = Query(...)) -> Dict[str, Any]:
    rules = [r.model_dump() for r in _rules.values()
             if r.org_id == org_id and r.project_id == project_id]
    return {"rules": rules, "total": len(rules)}


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(req: CreateRuleRequest) -> Dict[str, Any]:
    rule = AlertRule(**req.model_dump())
    _rules[rule.rule_id] = rule
    logger.info("Alert rule created", rule_id=rule.rule_id, name=rule.name)
    return {"rule_id": rule.rule_id, "message": "Alert rule created"}


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: str):
    if rule_id not in _rules:
        raise HTTPException(status_code=404, detail="Rule not found")
    del _rules[rule_id]


@router.get("")
async def list_alerts(
    org_id: str = Query(...),
    project_id: str = Query(None),
    severity: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    alerts = [a for a in _fired_alerts if a.org_id == org_id]
    if severity:
        alerts = [a for a in alerts if a.severity.value == severity]
    if resolved is not None:
        alerts = [a for a in alerts if (a.resolved_at is not None) == resolved]
    return {"alerts": [a.model_dump() for a in alerts[-limit:]], "total": len(alerts)}


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Query(...),
) -> Dict[str, Any]:
    for alert in _fired_alerts:
        if alert.alert_id == alert_id:
            alert.acknowledged = True
            alert.acknowledged_by = acknowledged_by
            return {"message": "Alert acknowledged", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail="Alert not found")
